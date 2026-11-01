package manaforge.protocol;

import java.io.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;

/** Owned PUBLIC diagnostic receiver only: never starts an engine or emits deck contents.
 * Parent supplies trusted expected pins and owns startup deadlines/child cleanup.
 * Input validation here is not an authenticated runtime-ready handshake. */
public final class LaunchBootstrapProbe {
    public static void main(String[] args) {
        try {
            if(args.length!=4)throw new IOException();
            InputStream input=System.in;
            String text=TextFrame.read(input);
            LaunchContracts.LaunchManifest manifest=LaunchManifestReader.parse(text,args[1],args[2],args[3]);
            if(manifest==null)throw new IOException();
            Path result=Paths.get(args[0]),temporary=Paths.get(args[0]+".tmp");
            Files.write(temporary,"{\"validated\":true}".getBytes(StandardCharsets.UTF_8));
            Files.move(temporary,result,StandardCopyOption.ATOMIC_MOVE);
            manifest=null;text=null; // Release our owned launch references before the lifeline wait.
            if(input.read()!=-1)throw new IOException();
        }catch(Exception failure){System.err.println("PRIVATE_LAUNCH_PROBE_FAILED");System.exit(2);}
    }
}
