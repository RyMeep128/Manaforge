/** Normal saved-deck entrypoint. All human responses come from the authenticated viewer.
 * Fixtures, ordered decks and response scripts are absent from this launch mode. */
public final class ManaforgeLiveGame {
    public static void main(String[] args) {
        if(args.length!=4){System.err.println("UNITY_GAME_ARGUMENTS");System.exit(2);}
        System.setProperty("manaforge.liveGame","true");System.setProperty("manaforge.coreCombat","true");
        System.setProperty("manaforge.coreFromOpening","true");System.setProperty("manaforge.completeGame","true");
        System.setProperty("manaforge.metadataContext",args[3]);
        System.setProperty("manaforge.paymentMode",System.getProperty("manaforge.paymentMode","AUTO"));
        ManaforgeLiveOpening.main(new String[]{args[0],args[1],args[2]});
    }
}
