import json
import urllib.request
import urllib.error
import os

SERVER = "http://localhost:5000"


NPC_PROFILES = {
    "Guardiano":      {"desc": "Una guardia sospettosa che protegge l'ingresso del dungeon.", "hostility": 70, "friendship": 0, "lingua": "italiano"},
    "Ahmed":          {"desc": "Un mercante ambulante astuto e caloroso.",                    "hostility": 20, "friendship": 0, "lingua": "italiano"},
    "Yuki":           {"desc": "Una studiosa giapponese fredda e metodica.",                  "hostility": 30, "friendship": 0, "lingua": "giapponese"},
    "Ivan":           {"desc": "Un guerriero russo taciturno che rispetta solo la forza.",    "hostility": 55, "friendship": 0, "lingua": "russo"},
    "Pierre":         {"desc": "Un nobile francese decaduto e nostalgico.",                   "hostility": 25, "friendship": 0, "lingua": "francese"},
    "Chen":           {"desc": "Un alchimista cinese eccentrico ossessionato dalla ricerca.", "hostility": 15, "friendship": 0, "lingua": "cinese"},
    "Maria":          {"desc": "Una guaritrice spagnola empatica e premurosa.",               "hostility": 10, "friendship": 5, "lingua": "spagnolo"},
    "ElderMarcus":    {"desc": "Un antico saggio custode della profezia.",                    "hostility": 10, "friendship": 5, "lingua": "inglese"},
    "Hans":           {"desc": "Un fabbro tedesco burbero e perfezionista.",                  "hostility": 40, "friendship": 0, "lingua": "tedesco"},
    "Fatima":         {"desc": "Una maga cerimoniale araba devota ai rituali.",               "hostility": 20, "friendship": 0, "lingua": "arabo"},
    "DottorYamamoto": {"desc": "Uno scienziato giapponese eccentrico.",                       "hostility": 35, "friendship": 0, "lingua": "giapponese"},
    "Olaf":           {"desc": "Un vichingo norvegese diretto e fiero.",                      "hostility": 60, "friendship": 0, "lingua": "norvegese"},
}



def post(endpoint, data):
    body = json.dumps(data).encode("utf-8")
    req  = urllib.request.Request(
        SERVER + endpoint,
        data    = body,
        headers = {"Content-Type": "application/json"},
        method  = "POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"error": str(e)}

def get(endpoint):
    try:
        with urllib.request.urlopen(SERVER + endpoint, timeout=5) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.URLError as e:
        return {"error": str(e)}



def barra(valore, larghezza=20):
    piena = int(valore / 100 * larghezza)
    return "[" + "#" * piena + "-" * (larghezza - piena) + "]"

def umore(hostility):
    if hostility >= 90: return "MOLTO OSTILE"
    if hostility >= 70: return "ostile"
    if hostility >= 50: return "diffidente"
    if hostility >= 35: return "neutro"
    if hostility >= 20: return "amichevole"
    return "ALLEATO"

def icona_sorgente(source):
    return {"retrieval": "[DB]", "ollama": "[AI]", "fallback": "[FB]"}.get(source, "[?]")

def stampa_lista_npc(profili):
    print("-" * 62)
    print(f"  {'NOME':<18} {'OSTILITA':>9}  {'UMORE':<16} {'LINGUA'}")
    print("-" * 62)
    for nome, p in profili.items():
        print(f"  {nome:<18} {p['hostility']:>5}/100  {umore(p['hostility']):<16} {p['lingua']}")
    print("-" * 62)

def stampa_header_npc(nome, profilo, debug):
    print()
    print("=" * 62)
    print(f"  NPC      : {nome}")
    print(f"  Profilo  : {profilo['desc']}")
    print(f"  Ostilita : {barra(profilo['hostility'])} {profilo['hostility']}/100  [{umore(profilo['hostility'])}]")
    print(f"  Amicizia : {barra(profilo['friendship'])} {profilo['friendship']}/100")
    print(f"  Lingua   : {profilo['lingua']}")
    print("-" * 62)
    print("  Comandi disponibili:")
    print("    /status        - stato dettagliato NPC corrente")
    print("    /npc <nome>    - cambia NPC con cui parlare")
    print("    /npcs          - lista di tutti gli NPC")
    print("    /reset         - resetta memoria e ostilita NPC corrente")
    print("    /resetall      - resetta tutti gli NPC")
    print("    /storia        - mostra cronologia dialogo")
    print("    /debug on|off  - mostra sorgente risposta [DB/AI/FB]")
    print("    exit           - esci dal programma")
    print("=" * 62)



def main():
    debug = False

    print("=" * 62)
    print("        ORACULUS AI  -  Sistema Dialogo NPC")
    print("        Motore: Retrieval + Ollama LLM  (100% offline)")
    print("=" * 62)
    print()

    health = get("/health")
    if "error" in health:
        print("  ERRORE: Server non raggiungibile.")
        print(f"  Assicurati che 'python ai_server.py' sia in esecuzione.")
        print(f"  Dettaglio: {health['error']}")
        return

    ollama_stato = "attivo" if health.get("ollama") else "non attivo (usa retrieval+fallback)"
    print(f"  Server:  online")
    print(f"  Dataset: {health.get('dataset', '?')} conversazioni")
    print(f"  Ollama:  {ollama_stato}")
    print()

    stampa_lista_npc(NPC_PROFILES)
    print()
    scelta_npc = input("Scegli NPC con cui iniziare (invio = Guardiano): ").strip()
    if scelta_npc not in NPC_PROFILES:
        scelta_npc = "Guardiano"

    npc_corrente = scelta_npc
    profilo      = NPC_PROFILES[npc_corrente]
    stampa_header_npc(npc_corrente, profilo, debug)

    
    while True:
        try:
            testo = input("Giocatore: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Arrivederci!")
            break

        if not testo:
            continue

        if testo == "exit":
            print("\n  Arrivederci!")
            break

        elif testo == "/status":
            p = profilo
            print(f"\n  NPC      : {npc_corrente}")
            print(f"  Ostilita : {barra(p['hostility'])} {p['hostility']}/100  [{umore(p['hostility'])}]")
            print(f"  Amicizia : {barra(p['friendship'])} {p['friendship']}/100")
            print(f"  Lingua   : {p['lingua']}")
            print(f"  Server   : {SERVER}")
            print(f"  Ollama   : {ollama_stato}")
            print()
            continue

        elif testo == "/npcs":
            stampa_lista_npc(NPC_PROFILES)
            continue

        elif testo.startswith("/npc "):
            nuovo = testo[5:].strip()
            if nuovo in NPC_PROFILES:
                npc_corrente = nuovo
                profilo      = NPC_PROFILES[npc_corrente]
                stampa_header_npc(npc_corrente, profilo, debug)
            else:
                print(f"  NPC '{nuovo}' non trovato. Usa /npcs per la lista.")
            continue

        elif testo == "/reset":
            result = post("/reset", {"npc_name": npc_corrente})
            profilo["hostility"]  = NPC_PROFILES[npc_corrente]["hostility"]
            profilo["friendship"] = NPC_PROFILES[npc_corrente]["friendship"]
            print(f"  Memoria e ostilita di {npc_corrente} resettate.")
            print()
            continue

        elif testo == "/resetall":
            post("/reset", {})
            for p in NPC_PROFILES.values():
                p["hostility"]  = 50
                p["friendship"] = 0
            print("  Tutti gli NPC resettati.")
            print()
            continue

        elif testo == "/storia":
            data    = get(f"/history/{npc_corrente}")
            storia  = data.get("history", [])
            if not storia:
                print(f"  Nessuna storia per {npc_corrente}.")
            else:
                print(f"\n  --- Storia con {npc_corrente} ---")
                for h in storia:
                    print(f"  Tu     : {h.get('player','')}")
                    print(f"  {npc_corrente}: {h.get('npc','')}")
                    print()
            continue

        elif testo.startswith("/debug"):
            parti = testo.split()
            if len(parti) > 1 and parti[1] == "on":
                debug = True
                print("  Debug attivato. Ogni risposta mostra [DB]=dataset [AI]=ollama [FB]=fallback")
            else:
                debug = False
                print("  Debug disattivato.")
            continue

        result = post("/chat", {
            "player_input": testo,
            "npc_name":     npc_corrente,
            "hostility":    profilo["hostility"],
            "friendship":   profilo["friendship"],
            "language":     profilo["lingua"],
        })

        if "error" in result:
            print(f"\n  [ERRORE] {result['error']}")
            print("  Verifica che 'python ai_server.py' sia ancora in esecuzione.")
            print()
            continue

        risposta      = result.get("response", "...")
        nuova_host    = result.get("new_hostility", profilo["hostility"])
        source        = result.get("source", "?")
        score         = result.get("retrieval_score", 0.0)
        intent        = result.get("intent", "?")
        delta         = nuova_host - profilo["hostility"]

        print()
        if debug:
            print(f"  {npc_corrente}: {risposta}  {icona_sorgente(source)}")
        else:
            print(f"  {npc_corrente}: {risposta}")

        delta_str = f"(+{delta})" if delta > 0 else f"({delta})" if delta < 0 else "(=)"
        print(f"\n  Ostilita : {barra(nuova_host)} {nuova_host}/100  [{umore(nuova_host)}]  {delta_str}")

        if debug:
            print(f"  Debug    : sorgente={source}  score={score:.3f}  intent={intent}")

        print()

        profilo["hostility"] = nuova_host

        if nuova_host >= 95:
            print("  ⚠️  ATTENZIONE: L'NPC sta per attaccare!")
            print()
        elif nuova_host <= 15 and profilo["friendship"] >= 20:
            print(f"  ✨ Hai guadagnato la piena fiducia di {npc_corrente}!")
            print()


if __name__ == "__main__":
    main()