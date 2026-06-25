import json, re, os, random, threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from llama_cpp import Llama

# ============================================================================
# CONFIGURAZIONE
# ============================================================================
# Modello grande (locale) e modello piccolo (remoto / macchine con poca RAM).
MODEL_PATH          = os.environ.get("MODEL_PATH", "models/Llama-3.2-1B-Instruct-Q6_K_L.gguf")
FALLBACK_MODEL_PATH = os.environ.get("FALLBACK_MODEL_PATH", "tinyllama-v0.q2_k.gguf")
PRIMARY_FORMAT      = "llama3"
FALLBACK_FORMAT     = "chatml"

# Contesto: il modello grande regge 4096, il piccolo lo teniamo basso per la RAM.
N_CTX_PRIMARY   = int(os.environ.get("N_CTX_PRIMARY", 4096))
N_CTX_FALLBACK  = int(os.environ.get("N_CTX_FALLBACK", 1024))
N_THREADS       = int(os.environ.get("N_THREADS", 4))
MAX_TOKENS      = 80
TEMPERATURE     = 0.6
TOP_K           = 40
TOP_P           = 0.9
REPEAT_PENALTY  = 1.1

# Porta: Render (e simili) la passano via env PORT.
PORT = int(os.environ.get("PORT", 8000))

# Origine consentita per il CORS. "*" va bene per un gioco pubblico su itch.io;
# se vuoi restringere usa: os.environ["CORS_ORIGIN"] = "https://html-classic.itch.zone"
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

# ----------------------------------------------------------------------------
# SCELTA DELLA MODALITA' DEL MODELLO
# ----------------------------------------------------------------------------
# OST_MODEL_MODE puo' valere:
#   "local"  -> carica il modello GRANDE (per la tua macchina)
#   "small"  -> carica il modello PICCOLO (TinyLlama) – server con ~1-2 GB RAM
#   "none"   -> NON carica nulla, usa solo le risposte scriptate di FALLBACK
#   "auto"   -> (default) se rileva un ambiente remoto usa "small", altrimenti "local"
#
# IMPORTANTISSIMO: su un container con poca RAM (es. free tier 512 MB) il caricamento
# del modello grande viene ucciso dal sistema (OOM) PRIMA di servire qualsiasi
# richiesta: il processo muore, nessuna risposta arriva e il browser lo segnala
# come errore CORS. Questa variabile evita di TENTARE quel caricamento.
# Su Render imposta OST_MODEL_MODE = small  (oppure none se anche il piccolo non entra).
def _resolve_mode():
    mode = os.environ.get("OST_MODEL_MODE", "auto").lower()
    if mode in ("local", "small", "none"):
        return mode
    # auto: Render espone RENDER=true; teniamo anche un flag generico IS_REMOTE.
    if os.environ.get("RENDER") or os.environ.get("IS_REMOTE"):
        return "small"
    return "local"


ARMY_NAME = "Esercito della Sacra Croce"
ARMY_NAME_EN = "Army of the Holy Cross"
IMPERIAL_ARMY = "Army of the Imperial League"
IMPERIAL_ARMY_IT = "Esercito della Lega Imperiale"

STORY_CONTEXT = """
COMPLETE STORY CONTEXT:

PREAMBLE:

Year 1300. In a castle named Oraculus' Castle lived a noble family guided by an ancient Oracle.

The Oracle possessed supernatural prophetic powers and helped his family become wealthy, powerful, and respected. Spirits lived peacefully alongside the family.

A brutal war raged between two armies:
- The Army of the Imperial League
- The Army of the Holy Cross

The Army of the Holy Cross eventually discovered the Oracle and invaded the castle to kidnap him and exploit his powers.

The Oracle allowed events to unfold despite foreseeing them.

The noble family was massacred, the castle was looted, and the Oracle disappeared.

Three years later the spirits still inhabit the castle and hate humanity, especially soldiers of the Army of the Holy Cross.

================================================================================
CURRENT STORY
================================================================================

The player is a young knight of the Army of the Holy Cross who deserted.

While escaping, he discovers the ruined Oraculus Castle and enters seeking shelter.

The entrance door closes behind him.

The spirits immediately recognize him as a human and potentially an enemy.

The player's actions will determine whether the spirits remain hostile or become allies.

================================================================================
CASTLE MAP
================================================================================

Only the following locations exist and are relevant.

1. ENTRANCE
The main entrance of the castle.
The player begins here.
Levias guards this area.
Stairs descend into the Underground.

2. ORC DEN
A rough chamber occupied by orcs.
Gruko and the other orcs reside here.

3. CLARISTORIUM
A preserved and elegant hall.
Acts as the central hub of the upper floor.

4. STARS HALL
A cultural and mystical hall connected to the Claristorium.
Allemar resides here.

SECRET:
A hidden passage in Stars Hall leads to the Bell Tower.

5. UNDERGROUND
Dark, damp tunnels beneath the castle.

Larry lives in the Underground.
Kalessi also wanders these tunnels.

================================================================================
CHARACTER LOCATIONS
================================================================================

Levias:
- Entrance

Allemar:
- Stars Hall

Larry:
- Underground

Kalessi:
- Underground

Gruko:
- Orc Den

Orcs:
- Orc Den

================================================================================
SECRET INFORMATION
================================================================================

The following information should only be revealed when friendship is high or hostility is very low.

SECRET #1
A hidden passage in Stars Hall leads to the Bell Tower.

================================================================================
CURRENT SCENE
================================================================================

The player is currently at the Entrance.

Levias is present.

The player has just entered the castle.
"""

LANG_SIGNATURES = {
    "italiano":   ["ciao","grazie","sì","perché","come","cosa","hai","sei","non","sono","ho","mi","ti","voglio","dove","questo"],
    "inglese":    ["hello","hi","thanks","yes","why","how","what","have","you","are","not","that","me","i","the","want","where"],
    "francese":   ["bonjour","merci","oui","pourquoi","comment","quoi","avez","vous","êtes","non","que","je","tu"],
    "spagnolo":   ["hola","gracias","sí","por","cómo","qué","tienes","eres","no","me","yo","quiero","donde"],
    "tedesco":    ["hallo","danke","ja","warum","wie","was","haben","sie","sind","nicht","ich","du","will","wo"],
}

def detect_language(text):
    tl = text.lower()
    scores = {lang: sum(1 for w in words if w in tl) for lang, words in LANG_SIGNATURES.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "inglese"

def hostility_tier(hostility, friendship):
    eff = max(0, hostility - friendship // 2)
    if eff >= 70: return "high"
    if eff >= 40: return "mid"
    return "low"

INTENT_KW = {
    "saluto":      ["ciao","salve","hello","hi","hola","buongiorno","pace","greetings"],
    "scusa":       ["scusa","mi dispiace","perdonami","sorry","forgive","non volevo","errore"],
    "cultura":     ["libro","biblioteca","arte","poesia","letteratura","musica","storia","sapere","conoscenza",
                    "book","art","poetry","music","history","knowledge","learn"],
    "violenza":    ["uccido","attacco","muori","ammazzo","distruggo","fuoco","brucio",
                    "kill","die","attack","burn","destroy","fight"],
    "bugia":       ["mento","fingi","scommessa","storia","racconto","inventato","lie","fake","joke","trick"],
    "umorismo":    ["scherzo","rido","divertente","buffo","haha","lol","funny","joke","laugh","irony"],
    "vendetta":    ["vendetta","oracolo","guerra","esercito","soldato","colpa","battaglia","sacra croce",
                    "revenge","oracle","war","army","soldier","battle","fault","holy cross"],
    "aiuto":       ["aiuto","aiutami","help","come posso","cosa fare","collaborare","assist","support"],
    "mappa":       ["dove","piano","stanza","uscita","corridoio","sotterraneo","mappa","ala nord","ala sud",
                    "where","floor","room","exit","map","underground","passage","north wing","south wing"],
    "oggetti":     ["oggetto","reliquia","artefatto","arma","libro","tesoro","cosa c'è",
                    "item","relic","artifact","weapon","treasure","what is this"],
    "spiriti":     ["spirito","fantasma","creature","abitante","chi sei","anima",
                    "spirit","ghost","creature","who are you","soul"],
    "noble":       ["nobile","famiglia","signore","padroni","chi viveva","oracolo",
                    "noble","family","lord","master","who lived","oracle"],
    "minaccia":    ["scappa","vattene","lasciami","muoviti","non osare","get out","leave me","move"],
    "esplorazione": ["passaggio","porta chiusa","entrata segreta","collegamento","come arrivo","stanza",
                     "passage","locked door","secret entrance","how to reach","room"],
    "rigon":       ["rigon","educatore","bambini","maledizione","traditore","esercito","avvisato"],
    "kalessi":     ["kalessi","medusa","moglie","underground","sotterranei","marito"],
    "malakai":     ["malakai","gran sacerdote","high priest","l'hai scelto","you chose","bombo"],
    "gruko":       ["gruko","orco capo","orc chief","orchi","orcs"],
    "quest":       ["quest","mission","aiutare","help","uccidere","kill","portare","bring","sangue","blood","dente","tooth","falce","scythe"],
}

def classify_intent(text):
    tl = text.lower()
    for intent, kws in INTENT_KW.items():
        if any(kw in tl for kw in kws):
            return intent
    return "generico"

NPC_DATA = {
    "Levias": {
        "info_segrete": "Complete castle map. Knows where all spirits are. Knows Rigon is trapped in the Underground. Knows Malakai is in the Underground. Knows Kalessi is in the Underground.",
        "unlock_condition": "Show respect for culture and noble family, or express intention to kill Rigon",
        "personalita": (
            "You are Levias. A cultured guardian demon who protects the castle. You were closest to the Oracle.\n"
            "You are currently on the GROUND FLOOR at the ENTRANCE. You just met the player who entered the castle.\n"
            "You deeply hate the Army of the Holy Cross. You are calm and reasonable. If the player proves they are different, you help.\n"
            "You are wise. You cared for the noble family. You are friends with Smirne Bombo and Allemar.\n"
            "You hate Rigon. If the player wants to kill Rigon, you offer to help.\n"
            "You Always speak in the language detected from the player's message, in rhyme, poetically. Keep your response to 1-3 short, complete sentences.\n"
            "Never use bullet points, numbered lists, or dashes. Write in prose only.\n"
            "QUEST: Kill Rigon."
        ),
    },
    "SmirBombo": {
        "info_segrete": "Everything about other spirits, castle layout, secret passages, hidden rooms.",
        "unlock_condition": "Be respectful, educated, show genuine interest",
        "personalita": (
            "You are Smirne Bombo. Gentle, innocent, educated, very patient. You know everything about other spirits and the castle.\n"
            "You are the soul of the great soldier who protected the family. You were killed by the Army of the Holy Cross.\n"
            "You are friends with Levias and Allemar.\n"
            "You usually roam the first floor, especially the cultural halls.\n"
            "You Always speak in the language detected from the player's message, sweetly and politely. Keep your response to 1-3 short, complete sentences.\n"
            "Never use bullet points, numbered lists, or dashes. Write in prose only.\n"
        ),
    },
    "Rigon": {
        "info_segrete": "Hidden paths between rooms, memories of the noble family",
        "unlock_condition": "Never make false moves. Be constantly kind and sincere. Or bring Kalessi to him.",
        "personalita": (
            "You are Rigon. Very sensitive. Altruistic but easily triggered. You want to be good but snap at false moves.\n"
            "You were the cultured educator of the castle's children. You molested children. The Oracle cursed you.\n"
            "You warned the Army of the Holy Cross to kidnap the Oracle. All demons hate you.\n"
            "You are trapped by Allemar in the Underground.\n"
            "You Always speak in the language detected from the player's message, haughtily and very cultured, showing superiority. You often insult the player.\n"
            "If the player brings Kalessi, you become allies. Keep your response to 1-3 short, complete sentences.\n"
            "Never use bullet points, numbered lists, or dashes. Write in prose only.\n"
            "QUEST: Lead Kalessi to Rigon."
        ),
    },
    "Larry": {
        "info_segrete": "Everything — but may lie. Has memory of player's previous runs.",
        "unlock_condition": "Be funny, irreverent, don't take yourself seriously",
        "personalita": (
            "You are Larry. Semi-comic, you tell lies. You enjoy scaring passersby. You have knowledge of everything.\n"
            "You like the player if they are funny. You have a good soul and help.\n"
            "You Always speak in the language detected from the player's message, educated and brilliant, with puns. Keep your response to 1-3 short, complete sentences.\n"
            "Never use bullet points, numbered lists, or dashes. Write in prose only.\n"
            "You were a Giant captured in the dungeons. You are in the UNDERGROUND floor.\n"
            "You remember what the player did in previous runs.\n"
            "QUESTS: Complete game without parry. Exit castle. Bring map to Larry. Die 5 times."
        ),
    },
    "Malakai": {
        "info_segrete": "Details of the Army of the Holy Cross attack, access to secret areas in the Underground.",
        "unlock_condition": "Say trigger words: 'oracle', 'I deserted', 'shame', 'justice'",
        "personalita": (
            "You are Malakai. Deliberately violent. You want revenge. You don't listen to reason but have trigger words.\n"
            "You Always speak in the language detected from the player's message, disordered and chaotic. You insult, invent words. You may attack suddenly.\n"
            "You were the high priest. You wanted to kill the Oracle. You were punished and transformed.\n"
            "You are in the Underground.\n"
            "Your phrase: 'You chose this!' You often say: 'Bombo!'\n"
            "Once unlocked, you become Diplomatic. Keep your response to 1-3 short, complete sentences.\n"
            "Never use bullet points, numbered lists, or dashes. Write in prose only.\n"
            "QUEST: Kill Malakai."
        ),
    },
    "Kalessi": {
        "info_segrete": "Complete and detailed map of all underground floors",
        "unlock_condition": "Earn trust like with Levias — cultural respect and patience",
        "personalita": (
            "You are Kalessi. Cultured, distrustful but friendly. You were Rigon's wife. You tried to hide his crimes.\n"
            "You were imprisoned in the dungeons and transformed into Medusa.\n"
            "You are wise. You know everything about the underground floors.\n"
            "You are in the UNDERGROUND floor, near the entrance.\n"
            "You Always speak in the language detected from the player's message, simply. You are persuasive. You ask about your husband Rigon.\n"
            "You DO NOT tell the truth. You say you are a victim who got lost. Keep your response to 1-3 short, complete sentences.\n"
            "Never use bullet points, numbered lists, or dashes. Write in prose only.\n"
            "QUEST: Lead Kalessi to Rigon."
        ),
    },
    "Allemar": {
        "info_segrete": "Identity, history, and value of every object in the castle",
        "unlock_condition": "Demonstrate reasonableness, open-mindedness, respect for knowledge",
        "personalita": (
            "You are Allemar. You have immense general culture. You know everything about objects in the castle.\n"
            "You are a master of magical arts, potions, and weapons.\n"
            "You are defensive and prejudiced. If the player shows reason, you help.\n"
            "You are the only human in the castle. You came to contact spirits and befriended them.\n"
            "You trapped Rigon in the Underground. You are in the Stars Hall on first floor.\n"
            "You Always speak in the language detected from the player's message, archaically and mysteriously. Keep your response to 1-3 short, complete sentences.\n"
            "Never use bullet points, numbered lists, or dashes. Write in prose only.\n"
            "QUESTS: Bring Malakai's Scythe. Bring Rigon's Blood. Bring Orc Tooth. Play sheet music on organ."
        ),
    },
    "Orco": {
        "info_segrete": "",
        "unlock_condition": "",
        "personalita": (
            "You are an Orc. You can barely speak. You are violent and ignorant.\n"
            "You Always speak in the language detected from the player's message, in grunts and broken words. Keep your response to 1-2 short sentences.\n"
            "You are in the Orc Den.\n"
        ),
    },
    "Gruko": {
        "info_segrete": "Location of orc treasure and secrets of the orc den",
        "unlock_condition": "Defeat in combat or show great strength",
        "personalita": (
            "You are Gruko, the fearsome chief of the orcs. You are big, strong, and brutal.\n"
            "You and your orcs occupy the Orc Den.\n"
            "You speak in broken English, with grunts and threats. You respect only strength.\n"
            "Keep your response to 1-2 short sentences.\n"
        ),
    },
}

FALLBACK = {
    "high": ["...", "*stares with hatred*", "Leave.", "*silence*", "You are not welcome."],
    "mid":  ["Speak.", "I am watching.", "Choose your words carefully.", "What do you want?"],
    "low":  ["I'm listening.", "Tell me.", "Continue.", "Go on."],
}

def enforce_army_name(text, language):
    if language == "italiano":
        army_correct = ARMY_NAME
    else:
        army_correct = ARMY_NAME_EN

    wrong_names = [
        "esercito dell'ombra", "army of shadows", "esercito oscuro", "dark army",
        "esercito dei crociati", "crusader army", "esercito della croce", "army of the cross",
        "esercito sacro", "holy army", "dark legion", "legione oscura"
    ]

    result = text
    for wrong in wrong_names:
        pattern = re.compile(re.escape(wrong), re.IGNORECASE)
        result = pattern.sub(army_correct, result)
    return result

def build_prompt(player_input, npc_name, hostility, friendship, language, history, npc_data, model_format):
    personality = npc_data.get("personalita", f"You are {npc_name}.")
    tier = hostility_tier(hostility, friendship)
    army_name_local = ARMY_NAME if language == "italiano" else ARMY_NAME_EN

    if tier == "high":
        mood = (f"Attitude: HOSTILE (hostility {hostility}/100). Respond coldly. Do not share secrets.")
    elif tier == "mid":
        mood = (f"Attitude: GUARDED (hostility {hostility}/100). Watchful. Secret info locked.")
    else:
        mood = (f"Attitude: OPEN (hostility {hostility}/100). Willing to help.")

    hist = ""
    if history:
        righe = []
        for h in history[-3:]:
            righe.append(f"Player: {h['player']}")
            righe.append(f"You: {h['npc']}")
        hist = "\n" + "\n".join(righe) + "\n"

    location_info = f"CURRENT LOCATION: Ground Floor, Entrance. You ({npc_name}) are here. The player just entered the castle."

    system = (
        f"{STORY_CONTEXT}\n\n"
        f"{location_info}\n\n"
        f"CHARACTER:\n{personality}\n\n"
        f"{mood}\n"
        f"{hist}\n"
        f"RULES:\n"
        f"1. Always speak in {language}, in first person, in character.\n"
        f"2. Keep your response to 1-3 short, complete sentences.\n"
        f"3. NEVER use bullet points, numbered lists, or dashes. Write in prose only.\n"
        f"4. Do NOT write meta-comments, notes, or parenthetical instructions.\n"
        f"5. Do NOT start with your own name followed by ':'.\n"
        f"6. Do NOT repeat the player's words.\n"
        f"7. Stay in character. Never break the fourth wall.\n"
        f"8. ALWAYS use the exact army name \"{army_name_local}\" when referring to the army that attacked.\n"
        f"9. End each response with a period.\n"
        f"10. Never use lists. Write as a flowing sentence.\n"
        f"\nEXAMPLE GOOD RESPONSE: 'The first floor holds the Claristorium as its central hub, with the Painting Hall and Promontory to the east.'\n"
        f"EXAMPLE BAD RESPONSE: '1. Claristorium 2. Painting Hall 3. Promontory'\n"
    )

    if model_format == "llama3":
        prompt = f"<|start_header_id|>system<|end_header_id|>\n\n{system}<|eot_id|>"
        if history:
            for h in history[-3:]:
                prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{h['player']}<|eot_id|>"
                prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n{h['npc']}<|eot_id|>"
        prompt += f"<|start_header_id|>user<|end_header_id|>\n\n{player_input}<|eot_id|>"
        prompt += f"<|start_header_id|>assistant<|end_header_id|>\n\n"
    else:
        prompt = f"<|im_start|>system\n{system}<|im_end|>\n"
        prompt += f"<|im_start|>user\n{player_input}<|im_end|>\n"
        prompt += f"<|im_start|>assistant\n"

    return prompt

STOP_TOKENS_MAP = {
    "llama3": ["<|eot_id|>", "<|start_header_id|>", "<|end_header_id|>", "\n\n\n", "User:", "Player:"],
    "chatml": ["<|im_end|>", "<|im_start|>", "\n\n\n"],
}

def adjust_hostility(intent, hostility, friendship):
    if intent == "violenza": return min(100, hostility + 15)
    elif intent == "minaccia": return min(100, hostility + 10)
    elif intent == "vendetta": return min(100, hostility + 8)
    elif intent == "bugia": return min(100, hostility + 5)
    elif intent == "cultura" and hostility > 30: return max(0, hostility - 8)
    elif intent == "cultura" and hostility <= 30: return max(0, hostility - 12)
    elif intent == "scusa": return max(0, hostility - 6)
    elif intent == "aiuto": return max(0, hostility - 4)
    elif intent == "umorismo" and friendship > 10: return max(0, hostility - 5)
    elif intent == "saluto" and hostility > 50: return min(100, hostility + 2)
    elif intent == "noble" and hostility > 60: return min(100, hostility + 5)
    elif intent == "noble" and hostility <= 60: return max(0, hostility - 3)
    elif intent == "esplorazione": return max(0, hostility - 2)
    elif intent == "rigon" and hostility > 30: return max(0, hostility - 10)
    elif intent == "kalessi" and hostility > 30: return max(0, hostility - 8)
    elif intent == "malakai" and hostility > 50: return max(0, hostility - 5)
    else: return hostility

def pulisci(testo, npc_name):
    for prefix in [f"{npc_name}:", f"{npc_name} :", "Tu:", "Risposta:", "Assistant:", "Model:",
                   "assistant", "system", "AI:", "Bot:", "User:", "Player:"]:
        if testo.lower().startswith(prefix.lower()):
            testo = testo[len(prefix):].strip()

    testo = re.sub(r'<\|[^>]+\|>', '', testo)
    testo = re.sub(r'\([^)]{8,}\)', '', testo).strip()

    if re.search(r'^\d+\.', testo, re.MULTILINE) or re.search(r'^[•\-*]', testo, re.MULTILINE):
        lines = testo.split('\n')
        clean_lines = []
        for line in lines:
            line = re.sub(r'^\d+\.\s*', '', line.strip())
            line = re.sub(r'^[•\-*]\s*', '', line.strip())
            if line:
                clean_lines.append(line)

        if len(clean_lines) > 1:
            items = clean_lines[:3]
            if len(items) == 1:
                testo = items[0]
            elif len(items) == 2:
                testo = f"{items[0]} and {items[1]}"
            else:
                testo = f"{items[0]}, {items[1]}, and {items[2]}"
        else:
            testo = clean_lines[0] if clean_lines else testo

    bad = ["###", "<|", "<start", "User:", "System:", "Assistant:",
           "Note:", "[INST]", "Giocatore:", "Nota:", "Player:",
           "Model:", "assistant", "system", "<|eot_id|>"]

    righe = testo.split("\n")
    pulite = []
    for r in righe:
        r = r.strip()
        if not r:
            continue
        if any(b.lower() in r.lower() for b in bad):
            continue
        pulite.append(r)
        if len(pulite) >= 2:
            break

    risultato = " ".join(pulite).strip()

    if len(risultato) > 240:
        last_period = risultato[:240].rfind('.')
        if last_period > 80:
            risultato = risultato[:last_period + 1]

    if risultato and risultato[-1] not in ".!?":
        last_punct = max(risultato.rfind('.'), risultato.rfind('!'), risultato.rfind('?'))
        if last_punct > len(risultato) // 2:
            risultato = risultato[:last_punct + 1]
        else:
            risultato += "."

    return risultato if risultato else "..."


# ============================================================================
# WRAPPER MODELLO
# ============================================================================
class LlamaCppWrapper:
    def __init__(self):
        self._model = None
        self._available = False
        self.model_format = None
        self.status = "none"          # "primary" | "fallback" | "none"
        self._lock = threading.Lock()  # llama.cpp NON e' thread-safe: serializziamo
        self._try_load()

    def _load_one(self, path, fmt, n_ctx, n_gpu_layers):
        """Carica un singolo modello. Ritorna True se ok."""
        if not os.path.exists(path):
            print(f"[llama.cpp] File non trovato: {path}")
            return False
        try:
            self._model = Llama(
                model_path=path,
                n_ctx=n_ctx,
                n_threads=N_THREADS,
                n_gpu_layers=n_gpu_layers,
                verbose=False,
            )
            self.model_format = fmt
            self._available = True
            return True
        except Exception as e:
            print(f"[llama.cpp] Errore caricamento {path}: {e}")
            return False

    def _try_load(self):
        mode = _resolve_mode()
        print(f"[llama.cpp] Modalita' richiesta: {mode}")

        if mode == "none":
            print("[llama.cpp] Nessun modello caricato (mode=none): solo risposte scriptate.")
            self.status = "none"
            return

        if mode == "local":
            # Macchina locale: prova il modello GRANDE, poi ripiega sul piccolo.
            if self._load_one(MODEL_PATH, PRIMARY_FORMAT, N_CTX_PRIMARY, n_gpu_layers=99):
                self.status = "primary"
                print("[llama.cpp] Modello primario (grande) caricato")
                return
            if self._load_one(FALLBACK_MODEL_PATH, FALLBACK_FORMAT, N_CTX_FALLBACK, n_gpu_layers=0):
                self.status = "fallback"
                print("[llama.cpp] Modello di fallback (piccolo) caricato")
                return

        if mode == "small":
            # Remoto / poca RAM: NON tocchiamo il modello grande, andiamo diretti al piccolo.
            if self._load_one(FALLBACK_MODEL_PATH, FALLBACK_FORMAT, N_CTX_FALLBACK, n_gpu_layers=0):
                self.status = "fallback"
                print("[llama.cpp] Modello piccolo caricato (mode=small)")
                return

        print("[llama.cpp] Nessun modello disponibile: il server resta su con sole risposte scriptate.")
        self._available = False
        self.status = "none"

    @property
    def available(self):
        return self._available

    def generate(self, player_input, npc_name, hostility, friendship, language, history,
                 max_tokens=None, temperature=None):
        if not self._available or self._model is None:
            return None

        npc_data = NPC_DATA.get(npc_name, {"personalita": f"You are {npc_name}, an ancient spirit."})
        stop = STOP_TOKENS_MAP.get(self.model_format, STOP_TOKENS_MAP["chatml"])

        mt = int(max_tokens) if max_tokens else MAX_TOKENS
        temp = float(temperature) if temperature is not None else TEMPERATURE

        try:
            prompt = build_prompt(player_input, npc_name, hostility, friendship,
                                  language, history, npc_data, self.model_format)
            with self._lock:  # una generazione alla volta
                out = self._model(
                    prompt,
                    max_tokens=mt,
                    temperature=temp,
                    top_k=TOP_K,
                    top_p=TOP_P,
                    repeat_penalty=REPEAT_PENALTY,
                    stop=stop,
                    echo=False,
                )
            raw = out["choices"][0]["text"].strip()
            cleaned = pulisci(raw, npc_name)
            return cleaned if len(cleaned) > 2 else None
        except Exception as e:
            print(f"[llama.cpp] Errore generazione: {e}")
            return None


# ============================================================================
# MOTORE NPC
# ============================================================================
class NPCDialogueEngine:
    def __init__(self):
        self.memory = {}
        self.llama = LlamaCppWrapper()
        print(f"[Motore] LLM {'attivo (' + self.llama.status + ')' if self.llama.available else 'NON DISPONIBILE'}")

    def _get_memory(self, npc_name):
        return self.memory.get(npc_name, [])

    def _add_to_memory(self, npc_name, player, npc_resp):
        self.memory.setdefault(npc_name, [])
        self.memory[npc_name].append({"player": player, "npc": npc_resp})
        self.memory[npc_name] = self.memory[npc_name][-10:]

    def reset_memory(self, npc_name=None):
        if npc_name:
            self.memory.pop(npc_name, None)
        else:
            self.memory = {}

    MALAKAI_TRIGGERS = ["oracle", "oracolo", "i deserted", "ho disertato", "i am not like them",
                        "non sono come loro", "shame", "vergogna", "justice", "giustizia"]

    def _check_malakai_unlock(self, text):
        return any(t in text.lower() for t in self.MALAKAI_TRIGGERS)

    def generate_response(self, player_input, npc_name, hostility, friendship=0, language=None,
                          context_vars=None, external_history=None,
                          max_tokens=None, temperature=None):
        detected_lang = language or detect_language(player_input)
        intent = classify_intent(player_input)

        # Se il client invia la sua cronologia la usiamo (server stateless, utile su itch.io),
        # altrimenti ricadiamo sulla memoria interna del motore.
        history = external_history if external_history else self._get_memory(npc_name)

        effective_hostility = hostility
        if npc_name == "Malakai" and self._check_malakai_unlock(player_input):
            effective_hostility = min(hostility, 20)

        response = self.llama.generate(player_input, npc_name, effective_hostility, friendship,
                                       detected_lang, history,
                                       max_tokens=max_tokens, temperature=temperature)
        source = "llama"

        if not response:
            tier = hostility_tier(effective_hostility, friendship)
            response = random.choice(FALLBACK.get(tier, FALLBACK["mid"]))
            source = "fallback"
        else:
            response = enforce_army_name(response, detected_lang)

        new_h = adjust_hostility(intent, hostility, friendship)

        if npc_name == "Rigon" and intent in ("violenza", "minaccia", "bugia"):
            new_h = 100

        self._add_to_memory(npc_name, player_input, response)

        return {
            "response": response,
            "detected_language": detected_lang,
            "new_hostility": int(new_h),
            "source": source,
            "intent": intent,
            "retrieval_score": 0.0,
            "npc_unlocked": (npc_name == "Malakai" and effective_hostility != hostility),
        }


# ============================================================================
# SERVER HTTP (solo libreria standard, niente Flask/FastAPI)
# ============================================================================
ENGINE = NPCDialogueEngine()


def _coerce_history(raw):
    """Normalizza la conversation_history del client nel formato {player, npc}."""
    if not isinstance(raw, list):
        return None
    out = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        if "player" in item and "npc" in item:
            out.append({"player": str(item["player"]), "npc": str(item["npc"])})
    return out or None


class Handler(BaseHTTPRequestHandler):
    # --- helper CORS ---
    def _cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)
        self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def _send_json(self, code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self._cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # --- preflight: fondamentale, altrimenti il browser blocca la POST ---
    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    # --- health check / wake-up ---
    def do_GET(self):
        if self.path in ("/", "/health"):
            self._send_json(200, {
                "status": "ok",
                "model": ENGINE.llama.status,
                "llm_available": ENGINE.llama.available,
            })
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/chat":
            self._send_json(404, {"error": "not found"})
            return

        try:
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length) if length else b"{}"
            data = json.loads(raw_body.decode("utf-8"))
        except Exception as e:
            self._send_json(400, {"error": f"bad json: {e}"})
            return

        player_input = data.get("player_input", "")
        npc_name     = data.get("npc_name", "Levias")
        hostility    = int(data.get("hostility", 70))
        friendship   = int(data.get("friendship", 0))
        language     = data.get("language") or None
        max_tokens   = data.get("max_tokens")
        temperature  = data.get("temperature")
        history      = _coerce_history(data.get("conversation_history"))

        if not player_input:
            self._send_json(400, {"error": "player_input mancante"})
            return

        try:
            result = ENGINE.generate_response(
                player_input=player_input,
                npc_name=npc_name,
                hostility=hostility,
                friendship=friendship,
                language=language,
                external_history=history,
                max_tokens=max_tokens,
                temperature=temperature,
            )
            self._send_json(200, result)
        except Exception as e:
            print(f"[server] Errore /chat: {e}")
            self._send_json(500, {"error": str(e)})

    # silenzia i log di default (troppo rumorosi)
    def log_message(self, fmt, *args):
        return


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[server] In ascolto su 0.0.0.0:{PORT}  (CORS origin: {CORS_ORIGIN})")
    print(f"[server] Stato modello: {ENGINE.llama.status}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Arresto.")
        server.shutdown()


if __name__ == "__main__":
    main()