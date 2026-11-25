# Searchable in-game choice menu

Creature-type choices use one engine-driven menu, including Cavern of Souls.
The initial **Your deck** tab contains only offered creature types printed on
that seat's submitted main deck and commander cards (including second faces).
It does not depend on what has been drawn, and does not inspect an opponent's
deck. Tokens created during play do not change this initial-deck summary.
**All types** shows every engine-offered type; search also searches all offered
types, regardless of the selected tab. An empty deck intersection stays empty
until the player searches or switches tabs. No type is selected automatically.

Selecting a row enables **Submit**. Typed text alone cannot create a choice.
Filtering preserves opaque option IDs. Required choices have no cancel action;
optional choices retain the engine's cancel action. The centered menu can be
minimized to view the battlefield and reopened without losing its search.
A new revision retires the old menu through the existing authenticated offer.

The gateway marks native `ChoiceCreatureType` callbacks with optional
`ChoiceRequest.menu = "creature_type"` and each option with optional `suggested`.
Only suggestion booleans are exported, never native sort keys or library IDs.
The full creature-type choice limit is 1024 (formerly 256); smaller engine
restrictions are preserved. Other native searchable choices reuse the component
with `menu = "search"` and retain their existing gateway bounds. Older snapshots
without these fields retain their existing UI. Java/C# models are generated from
the Python DTO schema.

This implements an Arena-style searchable selection flow with Manaforge theme
assets. Exact visual parity with Arena has not been established from a matching
reference capture; it must not be described as a verified pixel-for-pixel copy.

## Other card users

The pinned XMage source at `9068711bacbdc90247208ece155ee4fa7a6c9ba0` contains
109 card files that directly instantiate `ChoiceCreatureType` or
`ChooseCreatureTypeEffect`. All use the shared path automatically. Cards that
reach those choices through other shared effects also use it. This is a source
inventory, not individual card gameplay acceptance or an assertion about cards
missing from the pinned engine. The names below use the installed coverage audit
where available; unmatched entries retain their source class name.

| Card | Pinned engine source |
| --- | --- |
| Adaptive Automaton | `Mage.Sets/src/mage/cards/a/AdaptiveAutomaton.java` |
| An Unexpected Party // At the Door | `Mage.Sets/src/mage/cards/a/AnUnexpectedParty.java` |
| An-Zerrin Ruins | `Mage.Sets/src/mage/cards/a/AnZerrinRuins.java` |
| And They Shall Know No Fear | `Mage.Sets/src/mage/cards/a/AndTheyShallKnowNoFear.java` |
| Aphetto Dredging | `Mage.Sets/src/mage/cards/a/AphettoDredging.java` |
| Arcane Adaptation | `Mage.Sets/src/mage/cards/a/ArcaneAdaptation.java` |
| Ashes of the Fallen | `Mage.Sets/src/mage/cards/a/AshesOfTheFallen.java` |
| Banner of Kinship | `Mage.Sets/src/mage/cards/b/BannerOfKinship.java` |
| Belbe's Portal | `Mage.Sets/src/mage/cards/b/BelbesPortal.java` |
| Bloodline Bidding | `Mage.Sets/src/mage/cards/b/BloodlineBidding.java` |
| Bloodline Pretender | `Mage.Sets/src/mage/cards/b/BloodlinePretender.java` |
| Bloodline Shaman | `Mage.Sets/src/mage/cards/b/BloodlineShaman.java` |
| Brass Herald | `Mage.Sets/src/mage/cards/b/BrassHerald.java` |
| Caller of the Hunt | `Mage.Sets/src/mage/cards/c/CallerOfTheHunt.java` |
| Callous Oppressor | `Mage.Sets/src/mage/cards/c/CallousOppressor.java` |
| Cavern of Souls | `Mage.Sets/src/mage/cards/c/CavernOfSouls.java` |
| Celestial Reunion | `Mage.Sets/src/mage/cards/c/CelestialReunion.java` |
| Chronicle of Victory | `Mage.Sets/src/mage/cards/c/ChronicleOfVictory.java` |
| Circle of Solace | `Mage.Sets/src/mage/cards/c/CircleOfSolace.java` |
| Collective Inferno | `Mage.Sets/src/mage/cards/c/CollectiveInferno.java` |
| Conspiracy | `Mage.Sets/src/mage/cards/c/Conspiracy.java` |
| Coordinated Barrage | `Mage.Sets/src/mage/cards/c/CoordinatedBarrage.java` |
| Cover of Darkness | `Mage.Sets/src/mage/cards/c/CoverOfDarkness.java` |
| Crippling Fear | `Mage.Sets/src/mage/cards/c/CripplingFear.java` |
| Dawn-Blessed Pennant | `Mage.Sets/src/mage/cards/d/DawnBlessedPennant.java` |
| Defensive Maneuvers | `Mage.Sets/src/mage/cards/d/DefensiveManeuvers.java` |
| Distant Melody | `Mage.Sets/src/mage/cards/d/DistantMelody.java` |
| Doom Cannon | `Mage.Sets/src/mage/cards/d/DoomCannon.java` |
| Door of Destinies | `Mage.Sets/src/mage/cards/d/DoorOfDestinies.java` |
| Eclipsed Realms | `Mage.Sets/src/mage/cards/e/EclipsedRealms.java` |
| Elvish Soultiller | `Mage.Sets/src/mage/cards/e/ElvishSoultiller.java` |
| Engineered Plague | `Mage.Sets/src/mage/cards/e/EngineeredPlague.java` |
| Etchings of the Chosen | `Mage.Sets/src/mage/cards/e/EtchingsOfTheChosen.java` |
| Extinction | `Mage.Sets/src/mage/cards/e/Extinction.java` |
| For the Ancestors | `Mage.Sets/src/mage/cards/f/ForTheAncestors.java` |
| From the Rubble | `Mage.Sets/src/mage/cards/f/FromTheRubble.java` |
| Gathering Stone | `Mage.Sets/src/mage/cards/g/GatheringStone.java` |
| Grave Sifter | `Mage.Sets/src/mage/cards/g/GraveSifter.java` |
| Harmonized Crescendo | `Mage.Sets/src/mage/cards/h/HarmonizedCrescendo.java` |
| Harsh Mercy | `Mage.Sets/src/mage/cards/h/HarshMercy.java` |
| Haunting Voyage | `Mage.Sets/src/mage/cards/h/HauntingVoyage.java` |
| Herald's Horn | `Mage.Sets/src/mage/cards/h/HeraldsHorn.java` |
| Icon of Ancestry | `Mage.Sets/src/mage/cards/i/IconOfAncestry.java` |
| Instruments of War | `Mage.Sets/src/mage/cards/i/InstrumentsOfWar.java` |
| Karona, False God | `Mage.Sets/src/mage/cards/k/KaronaFalseGod.java` |
| Kindred Boon | `Mage.Sets/src/mage/cards/k/KindredBoon.java` |
| Kindred Charge | `Mage.Sets/src/mage/cards/k/KindredCharge.java` |
| Kindred Discovery | `Mage.Sets/src/mage/cards/k/KindredDiscovery.java` |
| Kindred Dominance | `Mage.Sets/src/mage/cards/k/KindredDominance.java` |
| Kindred Judgment | `Mage.Sets/src/mage/cards/k/KindredJudgment.java` |
| Kindred Summons | `Mage.Sets/src/mage/cards/k/KindredSummons.java` |
| Kolvori, God of Kinship // The Ringhart Crest | `Mage.Sets/src/mage/cards/k/KolvoriGodOfKinship.java` |
| Leyline of Transformation | `Mage.Sets/src/mage/cards/l/LeylineOfTransformation.java` |
| Lifecraft Engine | `Mage.Sets/src/mage/cards/l/LifecraftEngine.java` |
| Long List of the Ents | `Mage.Sets/src/mage/cards/l/LongListOfTheEnts.java` |
| Luminescent Rain | `Mage.Sets/src/mage/cards/l/LuminescentRain.java` |
| Metallic Mimic | `Mage.Sets/src/mage/cards/m/MetallicMimic.java` |
| Mirror of the Forebears | `Mage.Sets/src/mage/cards/m/MirrorOfTheForebears.java` |
| Mistform Sliver | `Mage.Sets/src/mage/cards/m/MistformSliver.java` |
| Mistform Wakecaster | `Mage.Sets/src/mage/cards/m/MistformWakecaster.java` |
| Molten Echoes | `Mage.Sets/src/mage/cards/m/MoltenEchoes.java` |
| Morophon, the Boundless | `Mage.Sets/src/mage/cards/m/MorophonTheBoundless.java` |
| New Blood | `Mage.Sets/src/mage/cards/n/NewBlood.java` |
| Obelisk of Urd | `Mage.Sets/src/mage/cards/o/ObeliskOfUrd.java` |
| Oko, Lorwyn Liege // Oko, Shadowmoor Scion | `Mage.Sets/src/mage/cards/o/OkoLorwynLiege.java` |
| Orcrist, Goblin-cleaver | `Mage.Sets/src/mage/cards/o/OrcristGoblinCleaver.java` |
| Outbreak | `Mage.Sets/src/mage/cards/o/Outbreak.java` |
| Pack's Disdain | `Mage.Sets/src/mage/cards/p/PacksDisdain.java` |
| Pact of the Serpent | `Mage.Sets/src/mage/cards/p/PactOfTheSerpent.java` |
| Patchwork Banner | `Mage.Sets/src/mage/cards/p/PatchworkBanner.java` |
| Patriarch's Bidding | `Mage.Sets/src/mage/cards/p/PatriarchsBidding.java` |
| Peer Pressure | `Mage.Sets/src/mage/cards/p/PeerPressure.java` |
| Pillar of Origins | `Mage.Sets/src/mage/cards/p/PillarOfOrigins.java` |
| Plague Engineer | `Mage.Sets/src/mage/cards/p/PlagueEngineer.java` |
| Pol Jamaar, Illusionist | `Mage.Sets/src/mage/cards/p/PolJamaarIllusionist.java` |
| Progenitor's Icon | `Mage.Sets/src/mage/cards/p/ProgenitorsIcon.java` |
| Radiant Destiny | `Mage.Sets/src/mage/cards/r/RadiantDestiny.java` |
| Raise the Palisade | `Mage.Sets/src/mage/cards/r/RaiseThePalisade.java` |
| Rally the Ranks | `Mage.Sets/src/mage/cards/r/RallyTheRanks.java` |
| Realmwalker | `Mage.Sets/src/mage/cards/r/Realmwalker.java` |
| Reflections of Littjara | `Mage.Sets/src/mage/cards/r/ReflectionsOfLittjara.java` |
| Renewed Solidarity | `Mage.Sets/src/mage/cards/r/RenewedSolidarity.java` |
| Riders of Gavony | `Mage.Sets/src/mage/cards/r/RidersOfGavony.java` |
| Rimefire Torque | `Mage.Sets/src/mage/cards/r/RimefireTorque.java` |
| Riptide Chronologist | `Mage.Sets/src/mage/cards/r/RiptideChronologist.java` |
| Riptide Replicator | `Mage.Sets/src/mage/cards/r/RiptideReplicator.java` |
| Riptide Shapeshifter | `Mage.Sets/src/mage/cards/r/RiptideShapeshifter.java` |
| Roaming Throne | `Mage.Sets/src/mage/cards/r/RoamingThrone.java` |
| Roar of the Crowd | `Mage.Sets/src/mage/cards/r/RoarOfTheCrowd.java` |
| Rukarumel, Biologist | `Mage.Sets/src/mage/cards/r/RukarumelBiologist.java` |
| Secluded Courtyard | `Mage.Sets/src/mage/cards/s/SecludedCourtyard.java` |
| Selective Snare | `Mage.Sets/src/mage/cards/s/SelectiveSnare.java` |
| Selfless Safewright | `Mage.Sets/src/mage/cards/s/SelflessSafewright.java` |
| Shared Triumph | `Mage.Sets/src/mage/cards/s/SharedTriumph.java` |
| Species Specialist | `Mage.Sets/src/mage/cards/s/SpeciesSpecialist.java` |
| Standardize | `Mage.Sets/src/mage/cards/s/Standardize.java` |
| Steely Resolve | `Mage.Sets/src/mage/cards/s/SteelyResolve.java` |
| Three Tree City | `Mage.Sets/src/mage/cards/t/ThreeTreeCity.java` |
| Titan of Littjara | `Mage.Sets/src/mage/cards/t/TitanOfLittjara.java` |
| Tribal Forcemage | `Mage.Sets/src/mage/cards/t/TribalForcemage.java` |
| Tribal Unity | `Mage.Sets/src/mage/cards/t/TribalUnity.java` |
| Tsabo's Decree | `Mage.Sets/src/mage/cards/t/TsabosDecree.java` |
| Unclaimed Territory | `Mage.Sets/src/mage/cards/u/UnclaimedTerritory.java` |
| Urza's Incubator | `Mage.Sets/src/mage/cards/u/UrzasIncubator.java` |
| Vanquisher's Banner | `Mage.Sets/src/mage/cards/v/VanquishersBanner.java` |
| Volrath's Laboratory | `Mage.Sets/src/mage/cards/v/VolrathsLaboratory.java` |
| Walking Desecration | `Mage.Sets/src/mage/cards/w/WalkingDesecration.java` |
| Witch's Vengeance | `Mage.Sets/src/mage/cards/w/WitchsVengeance.java` |
| Xenograft | `Mage.Sets/src/mage/cards/x/Xenograft.java` |

## Validation

Local graphics-enabled Unity coverage checks the deck-only default, off-deck
search, empty suggestions, explicit submission, option identity, virtualization,
centered gameplay overlay, and retirement on the next revision. Captures are
written to `Mtg_Projects/mtg_play_unity/Artifacts/ChoiceMenu/`.
Java coverage adds 300-option projection/opaque-key round trips, stale choices,
the 1024 bound, full-deck suggestions/copies, and restricted type lists.
Run Java/Python/protocol suites on GitHub Actions per the workspace policy.
Real-engine Cavern entry, restricted mana spending and uncounterability still
require packaged gameplay acceptance; UI fixture success does not prove them.
