# Peter Rabbit — branching narrative adapted from Beatrix Potter (public domain)
#
# Original: "The Tale of Peter Rabbit" (1893), Project Gutenberg #582.
# Simplified vocabulary for ages 3-5, branching structure with 4 endings.
# ~20 nodes, 5-8 nodes per playthrough (~3-4 minutes).

STORY = {
    "id": "peter_rabbit",
    "version": 1,
    "title": {"sv": "Pelle Kanin", "en": "Peter Rabbit"},
    "author": "Beatrix Potter",
    "age_min": 3,
    "age_max": 6,
    "estimated_minutes": 4,
    "narrate_choices": True,
    "start": "home",
    "nodes": {
        # --- ACT 1: The choice ---
        "home": {
            "text": {
                "sv": "Pelle Kanin bodde med sin mamma och sina systrar Fansen, Mansen och Bomansen under en stor gran. En dag sa mamman: Ga inte in i herr McGregors tradgard!",
                "en": "Peter Rabbit lived with his mother and his sisters Flopsy, Mopsy and Cotton-tail under a big fir tree. One day their mother said: Don't go into Mr McGregor's garden!",
            },
            "mood": "warm",
            "choices": [
                {
                    "label": {"sv": "Ga till tradgarden", "en": "Go to the garden"},
                    "next": "garden_gate",
                },
                {
                    "label": {"sv": "Plocka bar", "en": "Pick berries"},
                    "next": "berries",
                },
            ],
        },
        # --- Berry path (short happy ending) ---
        "berries": {
            "text": {
                "sv": "Pelle foljer sina systrar till busken med bjornbar. Solen varmer och baren ar sota och goda.",
                "en": "Peter follows his sisters to the blackberry bush. The sun is warm and the berries are sweet and delicious.",
            },
            "mood": "happy",
            "choices": [
                {
                    "label": {
                        "sv": "At bar med systrarna",
                        "en": "Eat berries with sisters",
                    },
                    "next": "berry_end",
                },
            ],
        },
        "berry_end": {
            "text": {
                "sv": "Pelle och systrarna at bar hela eftermiddagen. Nar de kom hem fick de brod och mjolk till middag. Vilken fin dag!",
                "en": "Peter and his sisters ate berries all afternoon. When they got home they had bread and milk for supper. What a lovely day!",
            },
            "mood": "happy",
            "ending": True,
            "ending_type": "happy",
        },
        # --- ACT 2: In the garden ---
        "garden_gate": {
            "text": {
                "sv": "Pelle krop under grinden in i herr McGregors tradgard. Dar vaxte morotter och sallad overallt!",
                "en": "Peter squeezed under the gate into Mr McGregor's garden. There were carrots and lettuces everywhere!",
            },
            "mood": "wonder",
            "choices": [
                {
                    "label": {"sv": "At morotter", "en": "Eat carrots"},
                    "next": "eating",
                },
                {
                    "label": {"sv": "Smyg forsiktigt", "en": "Sneak carefully"},
                    "next": "sneak",
                },
                {
                    "label": {"sv": "Leta efter radisor", "en": "Look for radishes"},
                    "next": "radishes",
                },
            ],
        },
        # --- Eating path (leads to chase) ---
        "eating": {
            "text": {
                "sv": "Pelle at morotter och sallad tills magen var rund. Plotsligt hordes en arg rost: Stanna tjuv!",
                "en": "Peter ate carrots and lettuces until his tummy was round. Suddenly an angry voice shouted: Stop thief!",
            },
            "mood": "tense",
            "sfx": "shout",
            "choices": [
                {
                    "label": {"sv": "Spring!", "en": "Run!"},
                    "next": "chase",
                },
                {
                    "label": {"sv": "Gom dig!", "en": "Hide!"},
                    "next": "toolshed",
                },
            ],
        },
        # --- Radish path (leads to chase via different route) ---
        "radishes": {
            "text": {
                "sv": "Pelle hittade stora fina radisor. Men nar han drog upp dem, borjade herr McGregor springa mot honom!",
                "en": "Peter found big beautiful radishes. But when he pulled them up, Mr McGregor started running towards him!",
            },
            "mood": "tense",
            "choices": [
                {
                    "label": {"sv": "Spring mot grinden!", "en": "Run to the gate!"},
                    "next": "gate_run",
                },
                {
                    "label": {
                        "sv": "Gom dig bakom buskarna",
                        "en": "Hide behind the bushes",
                    },
                    "next": "toolshed",
                },
            ],
        },
        # --- Sneak path (careful exploration) ---
        "sneak": {
            "text": {
                "sv": "Pelle smog tyst langs raderna med gronasaker. Han sag en damm dar en groda satt pa ett blad.",
                "en": "Peter crept quietly along the rows of vegetables. He saw a pond where a frog was sitting on a leaf.",
            },
            "mood": "wonder",
            "choices": [
                {
                    "label": {
                        "sv": "Fraga grodan om vagen",
                        "en": "Ask the frog the way",
                    },
                    "next": "frog",
                },
                {
                    "label": {"sv": "Smyg vidare", "en": "Sneak on"},
                    "next": "gate_run",
                },
            ],
        },
        "frog": {
            "text": {
                "sv": "Grodan blinkade med ett oga men svarade inte. Pelle gick forsiktigt vidare och hittade grinden!",
                "en": "The frog winked one eye but didn't answer. Peter walked carefully on and found the gate!",
            },
            "mood": "calm",
            "choices": [
                {
                    "label": {"sv": "Kryp under grinden", "en": "Crawl under the gate"},
                    "next": "safe_home",
                },
            ],
        },
        # --- Chase scene ---
        "chase": {
            "text": {
                "sv": "Pelle sprang sa fort han kunde! Han tappade sina skor bland kalhovedena och sin jacka vid hallon-busken.",
                "en": "Peter ran as fast as he could! He lost his shoes among the cabbages and his jacket by the raspberry bush.",
            },
            "mood": "tense",
            "choices": [
                {
                    "label": {"sv": "Spring mot natat", "en": "Run to the net"},
                    "next": "net",
                },
                {
                    "label": {
                        "sv": "Kryp in i vattkannan",
                        "en": "Climb in the watering can",
                    },
                    "next": "watering_can",
                },
            ],
        },
        # --- Net trap ---
        "net": {
            "text": {
                "sv": "Pelles knappar fastnade i ett krusbarsnat! Nagra sparvar flaxade och ropade: Skyda dig Pelle!",
                "en": "Peter's buttons got caught in a gooseberry net! Some sparrows fluttered down and cried: Hurry Peter!",
            },
            "mood": "tense",
            "choices": [
                {
                    "label": {"sv": "Vicka loss!", "en": "Wriggle free!"},
                    "next": "sneeze",
                },
            ],
        },
        "sneeze": {
            "text": {
                "sv": "Pelle vickade sig fri! Men sa naste han hogt. Atjo! Herr McGregor vande sig om.",
                "en": "Peter wriggled free! But then he sneezed loudly. Achoo! Mr McGregor turned around.",
            },
            "mood": "tense",
            "sfx": "sneeze",
            "choices": [
                {
                    "label": {"sv": "Spring mot grinden!", "en": "Run to the gate!"},
                    "next": "final_chase",
                },
            ],
        },
        # --- Watering can ---
        "watering_can": {
            "text": {
                "sv": "Pelle hoppade in i en vattenkanna. Brrr, vattnet var iskallt! Han naste hogt. Herr McGregor tittade dit!",
                "en": "Peter jumped into a watering can. Brrr, the water was ice cold! He sneezed loudly. Mr McGregor looked over!",
            },
            "mood": "tense",
            "choices": [
                {
                    "label": {"sv": "Hoppa ut och spring!", "en": "Jump out and run!"},
                    "next": "final_chase",
                },
            ],
        },
        # --- Toolshed ---
        "toolshed": {
            "text": {
                "sv": "Pelle smog in i redskapsboden och gomde sig i en kruka. Det var morkt och tyst. Han horde herr McGregor ga forbi.",
                "en": "Peter crept into the toolshed and hid in a flowerpot. It was dark and quiet. He heard Mr McGregor walk past.",
            },
            "mood": "calm",
            "choices": [
                {
                    "label": {
                        "sv": "Vanta tills det ar tyst",
                        "en": "Wait until it's quiet",
                    },
                    "next": "toolshed_escape",
                },
                {
                    "label": {"sv": "Titta ut", "en": "Peek out"},
                    "next": "gate_run",
                },
            ],
        },
        "toolshed_escape": {
            "text": {
                "sv": "Nar allt var tyst smog Pelle ut. Han hittade grinden och krop under den. Fri!",
                "en": "When all was quiet Peter crept out. He found the gate and squeezed under it. Free!",
            },
            "mood": "happy",
            "choices": [
                {
                    "label": {"sv": "Spring hem!", "en": "Run home!"},
                    "next": "brave_end",
                },
            ],
        },
        # --- Final chase to classic ending ---
        "final_chase": {
            "text": {
                "sv": "Pelle sprang och sprang! Han sag grinden! Han krop under den precis i tid.",
                "en": "Peter ran and ran! He saw the gate! He squeezed under it just in time.",
            },
            "mood": "tense",
            "choices": [
                {
                    "label": {"sv": "Spring hem!", "en": "Run home!"},
                    "next": "tea_end",
                },
            ],
        },
        # --- Gate run (converging node) ---
        "gate_run": {
            "text": {
                "sv": "Pelle sprang rakt mot grinden. Han sag den! Bara lite till!",
                "en": "Peter ran straight for the gate. He could see it! Just a little further!",
            },
            "mood": "tense",
            "choices": [
                {
                    "label": {
                        "sv": "Kryp under grinden!",
                        "en": "Crawl under the gate!",
                    },
                    "next": "safe_home",
                },
            ],
        },
        # --- ENDINGS ---
        "safe_home": {
            "text": {
                "sv": "Pelle kom hem utan att bli sedd! Han var trott men glad. Mamma kramade honom och han fick varm mjolk.",
                "en": "Peter got home without being seen! He was tired but happy. Mother hugged him and he had warm milk.",
            },
            "mood": "warm",
            "ending": True,
            "ending_type": "gentle",
        },
        "brave_end": {
            "text": {
                "sv": "Pelle var sa modig som gomde sig och vantade! Nar han kom hem beratade han allt for sina systrar.",
                "en": "Peter was so brave to hide and wait! When he got home he told his sisters all about it.",
            },
            "mood": "happy",
            "ending": True,
            "ending_type": "adventurous",
        },
        "tea_end": {
            "text": {
                "sv": "Pelle var sa trott nar han kom hem! Hans mamma la honom i sang och gav honom kamomillte. Hans systrar fick brod och bar till middag.",
                "en": "Peter was so tired when he got home! His mother put him to bed and gave him camomile tea. His sisters had bread and berries for supper.",
            },
            "mood": "warm",
            "ending": True,
            "ending_type": "classic",
        },
    },
}
