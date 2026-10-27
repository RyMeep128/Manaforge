"""Explicit standalone server commands; desktop startup never invokes these."""
import argparse
from getpass import getpass
import ipaddress
from pathlib import Path
import sys

from . import LibraryError
from .api import LibraryAPI
from .store import LibraryStore


def main():
    parser = argparse.ArgumentParser(description='Optional Manaforge Deck Library server')
    parser.add_argument('--data-dir', required=True, type=Path,
                        help='Private persistent directory outside the repository')
    commands = parser.add_subparsers(dest='command', required=True)
    init = commands.add_parser('init', help='Create a library and its first administrator')
    init.add_argument('--name', required=True)
    init.add_argument('--admin', required=True)
    serve = commands.add_parser('serve', help='Start the separate library service')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', default=8771, type=int)
    serve.add_argument('--lan', action='store_true', help='Explicitly permit a private LAN bind address')
    args = parser.parse_args()
    store = LibraryStore(args.data_dir)
    # User configuration and secrets must not be placed in a source checkout.
    package_root = Path(__file__).resolve().parents[4]
    if store.directory == package_root or package_root in store.directory.parents:
        parser.error('Choose a private data directory outside the source tree.')
    try:
        if args.command == 'init':
            password = getpass('Administrator password (12–256 characters): ')
            if password != getpass('Repeat administrator password: '):
                parser.error('Passwords do not match.')
            store.initialize(args.name, args.admin, password)
            print('Library initialized. No network service has been started.')
            return
        address = ipaddress.ip_address(args.host)
        if not address.is_loopback and not (args.lan and address.is_private and not address.is_unspecified):
            parser.error('Bind to loopback, or use --lan with a specific private LAN address.')
        if not 1 <= args.port <= 65535:
            parser.error('Port must be between 1 and 65535.')
        try:
            from waitress import serve as run_server
        except ImportError:
            parser.error('Install the optional requirements-library.txt before hosting.')
        app = LibraryAPI(store)
        print(f'Starting library on {address}:{args.port}. Stop with Ctrl+C.')
        # Ignore proxy headers. TLS terminates at the operator's tunnel/reverse proxy.
        # Waitress bounds concurrency, buffers and slow/incomplete requests.
        run_server(app, host=str(address), port=args.port, threads=4,
                   max_request_body_size=1024 * 1024, max_request_header_size=16384,
                   connection_limit=64, channel_timeout=30, clear_untrusted_proxy_headers=True)
    except (LibraryError, FileExistsError, ValueError) as error:
        print(str(error) if not isinstance(error, FileExistsError) else
              'Library already exists. Use serve; initialization never replaces existing data.', file=sys.stderr)
        raise SystemExit(1) from None
    except OSError:
        print('Cannot access library storage or bind the address. Check directory permissions and port availability.',
              file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == '__main__':
    main()
