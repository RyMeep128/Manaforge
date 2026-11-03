import com.google.gson.*;
import java.util.*;

/** Pinned native numeric/string response encoding. No damage or ordering rules live here. */
public final class NativeCombatChoices {
    private NativeCombatChoices(){}
    private static long integer(JsonObject row,String key) {
        JsonElement value=row.get(key);if(value==null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber() || !value.getAsString().matches("-?[0-9]+"))throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");
        long number=value.getAsLong();if(number<Integer.MIN_VALUE || number>Integer.MAX_VALUE)throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");return number;
    }
    public static JsonObject numericResponse(JsonObject prompt,JsonObject body) {
        String kind=prompt.get("kind").getAsString(),operation=body.get("operation").getAsString();long minimum=integer(prompt,"min"),maximum=integer(prompt,"max");if(minimum>maximum)throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");JsonObject result=new JsonObject();
        if("GAME_GET_AMOUNT".equals(kind) && "choose_number".equals(operation)){long value=integer(body,"value");if(value<minimum || value>maximum)throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");result.addProperty("kind","integer");result.addProperty("value",value);return result;}
        if(!"GAME_GET_MULTI_AMOUNT".equals(kind) || !"choose_amounts".equals(operation))throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");JsonArray ranges=prompt.getAsJsonArray("amounts"),values=body.getAsJsonArray("values");if(ranges.size()==0 || ranges.size()>256 || ranges.size()!=values.size())throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");long total=0;StringJoiner encoded=new StringJoiner(" ");
        for(int i=0;i<ranges.size();i++){JsonObject row=new JsonObject();row.add("value",values.get(i));long value=integer(row,"value"),min=integer(ranges.get(i).getAsJsonObject(),"min"),max=integer(ranges.get(i).getAsJsonObject(),"max");if(min>max || value<min || value>max)throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");total+=value;encoded.add(Long.toString(value));}
        if(total<minimum || total>maximum)throw new IllegalArgumentException("COMBAT_AMOUNT_INVALID");result.addProperty("kind","string");result.addProperty("value",encoded.toString());return result;
    }
    public static boolean matchesResponse(JsonObject prompt,JsonObject command) {
        try {
            String nativeKind=prompt.get("kind").getAsString(),kind=command.get("kind").getAsString();
            if("GAME_CHOOSE_CHOICE".equals(nativeKind) && "string".equals(kind)){String selected=command.get("value").getAsString();JsonElement keys=prompt.get("key_choices");if(keys!=null && keys.isJsonObject() && keys.getAsJsonObject().size()>0)return keys.getAsJsonObject().has(selected);JsonElement choices=prompt.get("choices");if(choices!=null && choices.isJsonArray())for(JsonElement choice:choices.getAsJsonArray())if(choice.isJsonPrimitive() && choice.getAsJsonPrimitive().isString() && selected.equals(choice.getAsString()))return true;return false;}
            JsonObject body=new JsonObject();if("GAME_GET_AMOUNT".equals(nativeKind) && "integer".equals(kind)){body.addProperty("operation","choose_number");body.add("value",command.get("value"));}
            else if("GAME_GET_MULTI_AMOUNT".equals(nativeKind) && "string".equals(kind)){String encoded=command.get("value").getAsString();if(encoded.length()>4096 || !encoded.matches("-?[0-9]+( -?[0-9]+)*"))return false;JsonArray values=new JsonArray();for(String value:encoded.split(" "))values.add(Long.parseLong(value));body.addProperty("operation","choose_amounts");body.add("values",values);}
            else return false;
            JsonObject expected=numericResponse(prompt,body);return expected.get("kind").equals(command.get("kind")) && expected.get("value").equals(command.get("value"));
        }catch(RuntimeException unsupported){return false;}
    }
}
