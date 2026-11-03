import java.io.OutputStreamWriter;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.Statement;
import com.google.gson.stream.JsonWriter;

/** Read an existing local catalog without bootstrapping XMage or changing its data. */
public final class XmageCatalogProbe {
    public static void main(String[] args) throws Exception {
        if (args.length != 1) throw new IllegalArgumentException("Expected an H2 database base path");
        String path = Path.of(args[0]).toAbsolutePath().toString().replace('\\', '/');
        if (path.indexOf(';') >= 0 || path.indexOf('\n') >= 0 || path.indexOf('\r') >= 0)
            throw new IllegalArgumentException("Invalid database path");
        String url = "jdbc:h2:file:" + path + ";ACCESS_MODE_DATA=r;IFEXISTS=TRUE;TRACE_LEVEL_FILE=0";
        try (Connection connection = DriverManager.getConnection(url, "", "");
             Statement statement = connection.createStatement();
             ResultSet rows = statement.executeQuery("SELECT NAME, SETCODE, CARDNUMBER, CLASSNAME, SECONDSIDENAME, DOUBLEFACEDSECONDSIDENAME, FLIPCARDNAME, SPELLOPTIONCARDNAME FROM CARD");
             JsonWriter writer = new JsonWriter(new OutputStreamWriter(System.out, StandardCharsets.UTF_8))) {
            writer.beginArray();
            while (rows.next()) {
                writer.beginObject();
                writer.name("name").value(rows.getString(1));
                writer.name("set_code").value(rows.getString(2));
                writer.name("collector_number").value(rows.getString(3));
                writer.name("class_name").value(rows.getString(4));
                writer.name("related_names").beginArray();
                for (int column = 5; column <= 8; column++) {
                    String related = rows.getString(column);
                    if (related != null && !related.isEmpty()) writer.value(related);
                }
                writer.endArray();
                writer.endObject();
            }
            writer.endArray();
        }
    }
}
