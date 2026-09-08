"""Bounded Scryfall-style query parser producing parameterized SQLite predicates.

Only explicitly supported operators compile; this is not full Scryfall parity.
The prints table is always referenced using alias p.
"""
import re


class LocalQueryError(ValueError):
    pass


def text_expression(field):
    return (f"coalesce(json_extract(s.search_json, '$.{field}'), '') || ' ' || "
            f"coalesce((SELECT group_concat(json_extract(face.value, '$.{field}'), ' ') "
            "FROM json_each(s.search_json, '$.card_faces') face), '')")


def compile_query(query):
    return Parser(query).parse()


class Parser:
    def __init__(self, query):
        if len(query) > 4096:
            raise LocalQueryError('Local search queries must be under 4096 characters.')
        self.tokens = []
        position = 0
        pattern = re.compile(r'\s+|[()]|(?:[^\s()"\\]+|"(?:\\.|[^"\\])*")+')
        while position < len(query):
            match = pattern.match(query, position)
            if match is None:
                raise LocalQueryError('Unclosed quote or invalid escape in local query.')
            token = match.group()
            if not token.isspace():
                self.tokens.append(token)
            position = match.end()
        if len(self.tokens) > 256:
            raise LocalQueryError('Local query has too many terms.')
        self.index = 0
        self.params = []

    def peek(self):
        return self.tokens[self.index] if self.index < len(self.tokens) else None

    def parse(self):
        if not self.tokens:
            return '1', []
        sql = self.expression(0)
        if self.peek() is not None:
            raise LocalQueryError('Unexpected closing parenthesis.')
        return sql, self.params

    def expression(self, depth):
        terms = [self.conjunction(depth)]
        while self.peek() and self.peek().upper() == 'OR':
            self.index += 1
            terms.append(self.conjunction(depth))
        return '(' + ' OR '.join(terms) + ')'

    def conjunction(self, depth):
        terms = [self.term(depth)]
        while self.peek() is not None and self.peek() != ')' and self.peek().upper() != 'OR':
            if self.peek().upper() == 'AND':
                self.index += 1
            terms.append(self.term(depth))
        return '(' + ' AND '.join(terms) + ')'

    def term(self, depth):
        if depth > 16:
            raise LocalQueryError('Local query nesting is too deep.')
        token = self.peek()
        if token is None or token == ')' or token.upper() in ('OR', 'AND'):
            raise LocalQueryError('Expected a search term.')
        self.index += 1
        if token == '-' or token.upper() == 'NOT':
            return 'NOT (' + self.term(depth + 1) + ')'
        if token == '(':
            sql = self.expression(depth + 1)
            if self.peek() != ')':
                raise LocalQueryError('Unclosed parenthesis.')
            self.index += 1
            return sql
        if token.startswith('-'):
            return 'NOT (' + self.atom(token[1:]) + ')'
        return self.atom(token)

    def bind(self, value):
        self.params.append(value)
        return '?'

    def atom(self, token):
        quoted_name = token.startswith('"')
        token = re.sub(r'"((?:\\.|[^"\\])*)"',
                       lambda m: re.sub(r'\\(.)', r'\1', m[1]), token)
        if not token:
            raise LocalQueryError('Search terms cannot be empty.')
        if quoted_name:
            return 'instr(lower(p.name), ' + self.bind(token.lower()) + ') > 0'
        match = re.fullmatch(r'([a-zA-Z_]+)(:|!=|>=|<=|=|>|<)(.+)', token)
        if not match:
            if re.match(r'[a-zA-Z_]+[:=<>]', token):
                raise LocalQueryError('Missing value after search operator.')
            if token.startswith('!'):
                return 'lower(p.name) = ' + self.bind(token[1:].lower())
            return 'instr(lower(p.name), ' + self.bind(token.lower()) + ') > 0'
        field, op, value = match.groups()
        field, value = field.lower(), value.lower()
        if value.startswith('/'):
            raise LocalQueryError('Regular expressions are not supported locally; use online search.')
        aliases = {'o': 'oracle', 't': 'type', 'ft': 'flavor', 'c': 'color',
                   'ci': 'identity', 'id': 'identity', 'e': 'set', 's': 'set',
                   'r': 'rarity', 'cmc': 'mv', 'pow': 'power', 'tou': 'toughness',
                   'loy': 'loyalty', 'f': 'legal', 'format': 'legal', 'n': 'name'}
        field = aliases.get(field, field)
        comparison = '=' if op == ':' else op
        if field in ('oracle', 'type', 'flavor', 'name'):
            if op not in (':', '=', '!='):
                raise LocalQueryError(f'{field} supports :, =, or != locally.')
            column = {'oracle': 'oracle_text_search', 'type': 'type_line', 'flavor': 'flavor_text', 'name': 'name'}[field]
            expr = 'p.name' if field == 'name' else text_expression(column)
            if op == ':':
                return f'instr(lower({expr}), {self.bind(value)}) > 0'
            return f'lower(trim({expr})) {comparison} {self.bind(value)}'
        if field in ('mv', 'power', 'toughness', 'loyalty', 'usd', 'eur', 'tix'):
            if not re.fullmatch(r'-?\d+(?:\.\d+)?', value):
                raise LocalQueryError(f'{field} needs a numeric value locally.')
            path = 'cmc' if field == 'mv' else 'prices.' + field if field in ('usd', 'eur', 'tix') else field
            def compare(source):
                expr = f"json_extract({source}, '$.{path}')"
                numeric = f"({expr} IS NOT NULL AND CAST({expr} AS TEXT) NOT GLOB '*[^0-9.-]*' AND CAST({expr} AS TEXT) GLOB '*[0-9]*')"
                return f'({numeric} AND CAST({expr} AS REAL) {comparison} {self.bind(float(value))})'
            sql = compare('s.search_json')
            if field in ('power', 'toughness', 'loyalty'):
                sql = f"({sql} OR EXISTS (SELECT 1 FROM json_each(s.search_json, '$.card_faces') face WHERE {compare('face.value')}))"
            return sql
        if field in ('color', 'identity'):
            return self.colors(field, op, value)
        if field in ('kw', 'keyword', 'game') and op in (':', '=', '!='):
            array = 'games' if field == 'game' else 'keywords'
            sql = f"EXISTS (SELECT 1 FROM json_each(s.search_json, '$.{array}') item WHERE lower(item.value) = {self.bind(value)})"
            return 'NOT ' + sql if op == '!=' else sql
        if field in ('otag', 'oracle_tag'):
            if op not in (':', '=', '!='):
                raise LocalQueryError('Oracle tags support otag:name or otag=name locally.')
            sql = ('EXISTS (SELECT 1 FROM oracle_tags tag '
                   'WHERE tag.oracle_id = p.oracle_id AND tag.tag = ' + self.bind(value) + ')')
            return 'NOT ' + sql if op == '!=' else sql
        if field in ('set', 'rarity', 'layout', 'lang', 'cn', 'artist'):
            if op not in (':', '=', '!='):
                raise LocalQueryError(f'{field} supports :, =, or != locally.')
            expr = {'set': 'p.set_code', 'cn': 'p.collector_number'}.get(field,
                    f"json_extract(s.search_json, '$.{field}')")
            if field == 'rarity':
                value = {'c': 'common', 'u': 'uncommon', 'r': 'rare', 'm': 'mythic'}.get(value, value)
            return f"lower(coalesce({expr}, '')) {comparison} {self.bind(value)}"
        if field in ('legal', 'banned', 'restricted'):
            if op != ':' or not re.fullmatch(r'[a-z]+', value):
                raise LocalQueryError('Use legal:format, banned:format, or restricted:format.')
            value = {'edh': 'commander'}.get(value, value)
            return f"json_extract(s.search_json, {self.bind('$.legalities.' + value)}) = {self.bind(field)}"
        if field in ('is', 'has') and op == ':':
            if value in ('foil', 'digital', 'reserved', 'reprint', 'promo'):
                return f"json_extract(s.search_json, '$.{value}') = 1"
            if value in ('dfc', 'double-faced'):
                return "json_extract(s.search_json, '$.layout') IN ('transform', 'modal_dfc', 'double_faced_token', 'reversible_card')"
            if value == 'token':
                return "json_extract(s.search_json, '$.layout') IN ('token', 'double_faced_token')"
        raise LocalQueryError(f'Unsupported local search filter: {field}{op}{value}. Use online search for this filter.')

    def colors(self, field, op, value):
        path = 'color_identity' if field == 'identity' else 'colors'
        color_rows = f"SELECT lower(value) AS value FROM json_each(s.search_json, '$.{path}')"
        if field == 'color':
            color_rows += (" UNION SELECT lower(color.value) FROM json_each(s.search_json, '$.card_faces') face, "
                           "json_each(face.value, '$.colors') color WHERE json_type(s.search_json, '$.colors') IS NULL")
        count = f'(SELECT count(DISTINCT value) FROM ({color_rows}))'
        if value in ('m', 'multicolor'):
            if op not in (':', '=', '!='):
                raise LocalQueryError('Use c:m or -c:m for multicolor cards.')
            return f'{count} {"<=" if op == "!=" else ">"} 1'
        if value.isdigit():
            return f'{count} {"=" if op == ":" else op} {self.bind(int(value))}'
        value = {'white': 'w', 'blue': 'u', 'black': 'b', 'red': 'r', 'green': 'g',
                 'colorless': '', 'c': ''}.get(value, value)
        if any(c not in 'wubrg' for c in value):
            raise LocalQueryError('Local colors use WUBRG letters or individual color names.')
        wanted = set(value)
        def contains(color):
            return f"EXISTS (SELECT 1 FROM ({color_rows}) color WHERE color.value = {self.bind(color)})"
        # Scryfall id: means within identity; c: means includes colors.
        colorless_shorthand = not wanted and op == ':'
        op = ('<=' if field == 'identity' else '>=') if op == ':' else op
        if colorless_shorthand:
            op = '='
        required = []
        if op in ('=', '!=', '>=', '>'):
            required += [contains(c) for c in sorted(wanted)]
        if op in ('=', '!=', '<=', '<'):
            required += ['NOT ' + contains(c) for c in sorted(set('wubrg') - wanted)]
        if op in ('>', '<'):
            required.append(f"{count} {'>' if op == '>' else '<'} {self.bind(len(wanted))}")
        sql = '(' + ' AND '.join(required or ['1']) + ')'
        return 'NOT ' + sql if op == '!=' else sql
