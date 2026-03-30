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
                "sv": "Pelle Kanin bodde med sin mamma och sina systrar Fansen, Mansen och Bomansen under en stor gran. En dag sa mamman: Gå inte in i herr Grävlings trädgård!",
                "en": "Peter Rabbit lived with his mother and his sisters Flopsy, Mopsy and Cotton-tail under a big fir tree. One day their mother said: Don't go into Mr McGregor's garden!",
            },
            "mood": "warm",
            "choices": [
                {
                    "label": {"sv": "Gå till trädgården", "en": "Go to the garden"},
                    "next": "garden_gate",
                },
                {
                    "label": {"sv": "Plocka bär", "en": "Pick berries"},
                    "next": "berries",
                },
            ],
        },
        # --- Berry path (short happy ending) ---
        "berries": {
            "text": {
                "sv": "Pelle följer sina systrar till busken med björnbär. Solen värmer och bären är söta och goda.",
                "en": "Peter follows his sisters to the blackberry bush. The sun is warm and the berries are sweet and delicious.",
            },
            "mood": "happy",
            "choices": [
                {
                    "label": {
                        "sv": "Ät bär med systrarna",
                        "en": "Eat berries with sisters",
                    },
                    "next": "berry_end",
                },
            ],
        },
        "berry_end": {
            "text": {
                "sv": "Pelle och systrarna åt bär hela eftermiddagen. När de kom hem fick de bröd och mjölk till middag. Vilken fin dag!",
                "en": "Peter and his sisters ate berries all afternoon. When they got home they had bread and milk for supper. What a lovely day!",
            },
            "mood": "happy",
            "ending": True,
            "ending_type": "happy",
        },
        # --- ACT 2: In the garden ---
        "garden_gate": {
            "text": {
                "sv": "Pelle kröp under grinden in i herr Grävlings trädgård. Där växte morötter och sallad överallt!",
                "en": "Peter squeezed under the gate into Mr McGregor's garden. There were carrots and lettuces everywhere!",
            },
            "mood": "wonder",
            "choices": [
                {
                    "label": {"sv": "Ät morötter", "en": "Eat carrots"},
                    "next": "eating",
                },
                {
                    "label": {"sv": "Smyg försiktigt", "en": "Sneak carefully"},
                    "next": "sneak",
                },
                {
                    "label": {"sv": "Leta efter rädisor", "en": "Look for radishes"},
                    "next": "radishes",
                },
            ],
        },
        # --- Eating path (leads to chase) ---
        "eating": {
            "text": {
                "sv": "Pelle åt morötter och sallad tills magen var rund. {pause} Plötsligt hördes en arg röst: {pause} Stanna tjuv!",
                "en": "Peter ate carrots and lettuces until his tummy was round. {pause} Suddenly an angry voice shouted: {pause} Stop thief!",
            },
            "mood": "tense",
            "sfx": "shout",
            "choices": [
                {
                    "label": {"sv": "Spring!", "en": "Run!"},
                    "next": "chase",
                },
                {
                    "label": {"sv": "Göm dig!", "en": "Hide!"},
                    "next": "toolshed",
                },
            ],
        },
        # --- Radish path (leads to chase via different route) ---
        "radishes": {
            "text": {
                "sv": "Pelle hittade stora fina rädisor. Men när han drog upp dem, började herr Grävling springa mot honom!",
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
                        "sv": "Göm dig bakom buskarna",
                        "en": "Hide behind the bushes",
                    },
                    "next": "toolshed",
                },
            ],
        },
        # --- Sneak path (careful exploration) ---
        "sneak": {
            "text": {
                "sv": "Pelle smög tyst längs raderna med grönsaker. Han såg en damm där en groda satt på ett blad.",
                "en": "Peter crept quietly along the rows of vegetables. He saw a pond where a frog was sitting on a leaf.",
            },
            "mood": "wonder",
            "choices": [
                {
                    "label": {
                        "sv": "Fråga grodan om vägen",
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
                "sv": "Grodan blinkade med ett öga men svarade inte. Pelle gick försiktigt vidare och hittade grinden!",
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
                "sv": "Pelle sprang så fort han kunde! Han tappade sina skor bland kålhuvudena och sin jacka vid hallonbusken.",
                "en": "Peter ran as fast as he could! He lost his shoes among the cabbages and his jacket by the raspberry bush.",
            },
            "mood": "tense",
            "choices": [
                {
                    "label": {"sv": "Spring mot nätet", "en": "Run to the net"},
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
                "sv": "Pelles knappar fastnade i ett krusbärsnät! Några sparvar flaxade och ropade: Skynda dig Pelle!",
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
                "sv": "Pelle vickade sig fri! Men så nös han högt. Atjoo! {pause} Herr Grävling vände sig om.",
                "en": "Peter wriggled free! But then he sneezed loudly. Achoo! {pause} Mr McGregor turned around.",
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
                "sv": "Pelle hoppade in i en vattenkanna. Brrr, vattnet var iskallt! Han nös högt. {pause} Herr Grävling tittade dit!",
                "en": "Peter jumped into a watering can. Brrr, the water was ice cold! He sneezed loudly. {pause} Mr McGregor looked over!",
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
                "sv": "Pelle smög in i redskapsboden och gömde sig i en kruka. Det var mörkt och tyst. Han hörde herr Grävling gå förbi.",
                "en": "Peter crept into the toolshed and hid in a flowerpot. It was dark and quiet. He heard Mr McGregor walk past.",
            },
            "mood": "calm",
            "choices": [
                {
                    "label": {
                        "sv": "Vänta tills det är tyst",
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
                "sv": "När allt var tyst smög Pelle ut. Han hittade grinden och kröp under den. {pause} Fri!",
                "en": "When all was quiet Peter crept out. He found the gate and squeezed under it. {pause} Free!",
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
                "sv": "Pelle sprang och sprang! Han såg grinden! Han kröp under den precis i tid.",
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
                "sv": "Pelle sprang rakt mot grinden. Han såg den! Bara lite till!",
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
                "sv": "Pelle kom hem utan att bli sedd! Han var trött men glad. Mamma kramade honom och han fick varm mjölk.",
                "en": "Peter got home without being seen! He was tired but happy. Mother hugged him and he had warm milk.",
            },
            "mood": "warm",
            "ending": True,
            "ending_type": "gentle",
        },
        "brave_end": {
            "text": {
                "sv": "Pelle var så modig som gömde sig och väntade! När han kom hem berättade han allt för sina systrar.",
                "en": "Peter was so brave to hide and wait! When he got home he told his sisters all about it.",
            },
            "mood": "happy",
            "ending": True,
            "ending_type": "adventurous",
        },
        "tea_end": {
            "text": {
                "sv": "Pelle var så trött när han kom hem! Hans mamma la honom i säng och gav honom kamomillte. Hans systrar fick bröd och bär till middag.",
                "en": "Peter was so tired when he got home! His mother put him to bed and gave him camomile tea. His sisters had bread and berries for supper.",
            },
            "mood": "warm",
            "ending": True,
            "ending_type": "classic",
        },
    },
}
