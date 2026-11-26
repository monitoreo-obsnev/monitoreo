import es.ugr.monitoreo.campo.Net;

import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Prueba en el escritorio el flujo de la cuenta de servicio de Net.java: java TestAuth clave.json > token.json */
public class TestAuth {
    static String field(String json, String name) {
        Matcher m = Pattern.compile("\"" + name + "\"\\s*:\\s*\"((?:[^\"\\\\]++|\\\\.)*+)\"").matcher(json);
        if (!m.find()) throw new RuntimeException("no " + name);
        return m.group(1).replace("\\n", "\n").replace("\\/", "/");
    }

    public static void main(String[] a) throws Exception {
        String json = new String(Files.readAllBytes(Paths.get(a[0])), "UTF-8");
        String out = Net.serviceAccountToken(field(json, "client_email"), field(json, "private_key"), Net.TOKEN_URI);
        System.out.println(out.trim().replaceAll("}$", ",\"project\":\"" + field(json, "project_id") + "\"}"));
    }
}
