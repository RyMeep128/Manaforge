package manaforge.protocol;
import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.concurrent.*;
public final class HistoryFixtureConsumer {
    public static void main(String[] args) throws Exception {
        JsonObject corpus=JsonParser.parseString(new String(Files.readAllBytes(Paths.get(args[0])),StandardCharsets.UTF_8)).getAsJsonObject();
        for(JsonElement item:corpus.getAsJsonArray("cases")) {
            JsonObject test=item.getAsJsonObject();
            try(ReceiveHistory history=new ReceiveHistory("fixture-session","one",test.get("fixture_mode").getAsBoolean(),test.get("capacity").getAsInt())) {
                for(JsonElement element:test.getAsJsonArray("steps")) {
                    JsonObject step=element.getAsJsonObject();String outcome=step.get("outcome").getAsString(),text=step.get("envelope").toString();
                    if(outcome.equals("applied") || outcome.equals("duplicate")) {
                        if((history.accept(text)!=null)!=outcome.equals("applied"))throw new AssertionError(test.get("name"));
                    } else {
                        try{history.accept(text);throw new AssertionError("Accepted "+test.get("name"));}
                        catch(WireEnvelope.EnvelopeException error){if(!error.code.equals(outcome) || !error.getMessage().equals(error.code))throw new AssertionError(test.get("name")+" "+error.code);}
                    }
                }
            }
        }
        String snapshot=corpus.getAsJsonArray("cases").get(0).getAsJsonObject().getAsJsonArray("steps").get(0).getAsJsonObject().get("envelope").toString();
        ReceiveHistory history=new ReceiveHistory("fixture-session","one",true,4096);
        history.accept(snapshot).getAsJsonObject("body").getAsJsonObject("snapshot").addProperty("turn",99);
        if(history.accept(snapshot)!=null || history.revision()!=7 || history.size()!=1)throw new AssertionError("Mutable retention");
        history.close();history.close();if(history.size()!=0)throw new AssertionError("Retained history");
        try{history.accept(snapshot);throw new AssertionError("Accepted after close");}catch(WireEnvelope.EnvelopeException error){if(!error.code.equals("HISTORY_CLOSED"))throw error;}
        for(int capacity:new int[]{0,65537})try{new ReceiveHistory("s","v",true,capacity);throw new AssertionError("Invalid capacity");}catch(IllegalArgumentException expected){}
        ExecutorService pool=Executors.newFixedThreadPool(8);
        try(ReceiveHistory concurrent=new ReceiveHistory("fixture-session","one",true,4096)) {
            List<Callable<Boolean>> tasks=new ArrayList<>();for(int i=0;i<8;i++)tasks.add(()->concurrent.accept(snapshot)!=null);
            int applied=0;for(Future<Boolean> future:pool.invokeAll(tasks))if(future.get())applied++;
            if(applied!=1 || concurrent.size()!=1)throw new AssertionError("Concurrent duplicate");
        } finally{pool.shutdownNow();}
        System.out.println("Receive history: "+corpus.getAsJsonArray("cases").size()+" sequences plus mutation, concurrency, capacity and disposal passed");
    }
}
