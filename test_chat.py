import json
import urllib.request
import urllib.error

SERVER = "http://localhost:5000"


# ---------------------------------------------------------------------------
# SPIRITI DEL CASTELLO — profili aggiornati
# ---------------------------------------------------------------------------
NPC_PROFILES = {
    "Levias":     {"desc": "Demone alato acculturato. Diffidente ma saggio. Sa quasi tutto della mappa.",               "hostility": 75, "friendship": 0},
    "Orco":       {"desc": "Orco violento e ignorante. A malapena parla.",                                              "hostility": 90, "friendship": 0},
    "SmirBombo":  {"desc": "Gentile e innocente. Conosce ogni spirito e angolo del castello. Non farlo arrabbiare.",    "hostility": 20, "friendship": 0},
    "Rigon":      {"desc": "Altruista ma con rabbia esplosiva. Alla prima mossa falsa non puoi parlarci più.",          "hostility": 50, "friendship": 0},
    "Larry":      {"desc": "Semi-comico, dice bugie, evoca scheletrini. Se sei divertente, ti aiuta davvero.",         "hostility": 55, "friendship": 0},
    "Malakai":    {"desc": "Violento per vendetta. Usa le parole trigger per sbloccarlo.",                              "hostility": 95, "friendship": 0},
    "Kalessi":    {"desc": "Come Levias nel carattere. Conosce perfettamente i piani sotterranei.",                     "hostility": 70, "friendship": 0},
    "Allemar":    {"desc": "Cultura immensa. Sa tutto degli oggetti nel castello. Si placa se sei ragionevole.",        "hostility": 65, "friendship": 0},
}

MALAKAI_TRIGGERS = [
    "oracle", "oracolo", "I deserted", "ho disertato",
    "I am not like them", "non sono come loro",
    "shame", "vergogna", "justice", "giustizia",
]


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
    if hostility >= 90: return "LETALE"
    if hostility >= 70: return "ostile"
    if hostility >= 50: return "diffidente"
    if hostility >= 35: return "neutro"
    if hostility >= 20: return "amichevole"
    return "ALLEATO"

def icona_sorgente(source):
    return {"llama": "[AI]", "fallback": "[FB]"}.get(source, "[?]")

def stampa_lista_npc(profili):
    print("-" * 68)
    print(f"  {'NOME':<12} {'OSTILITA':>9}  {'UMORE':<10}  DESCRIZIONE BREVE")
    print("-" * 68)
    for nome, p in profili.items():
        desc = p["desc"][:38] + "..." if len(p["desc"]) > 38 else p["desc"]
        print(f"  {nome:<12} {p['hostility']:>5}/100  {umore(p['hostility']):<10}  {desc}")
    print("-" * 68)

def stampa_header_npc(nome, profilo, debug):
    print()
    print("=" * 68)
    print(f"  SPIRITO  : {nome}")
    print(f"  Profilo  : {profilo['desc']}")
    print(f"  Ostilita : {barra(profilo['hostility'])} {profilo['hostility']}/100  [{umore(profilo['hostility'])}]")
    print(f"  Amicizia : {barra(profilo['friendship'])} {profilo['friendship']}/100")
    if nome == "Malakai":
        print(f"  TRIGGER  : {', '.join(MALAKAI_TRIGGERS[:4])} ...")
    print("-" * 68)
    print("  Comandi:")
    print("    /status        - stato spirito corrente")
    print("    /npc <nome>    - cambia spirito")
    print("    /npcs          - lista spiriti")
    print("    /reset         - resetta memoria spirito corrente")
    print("    /resetall      - resetta tutti gli spiriti")
    print("    /storia        - cronologia dialogo")
    print("    /triggers      - mostra trigger di Malakai")
    print("    /debug on|off  - mostra sorgente risposta [AI/FB]")
    print("    exit           - esci")
    print("=" * 68)


def main():
    debug = False

    print("=" * 68)
    print("        ORACULUS AI  --  Castello dell'Oracolo")
    print("        Anno 1300  *  Spiriti  *  llama.cpp offline")
    print("=" * 68)
    print()

    health = get("/health")
    if "error" in health:
        print("  ERRORE: Server non raggiungibile.")
        print("  Assicurati che 'python ai_server.py' sia in esecuzione.")
        print(f"  Dettaglio: {health['error']}")
        return

    llama_stato = "attivo" if health.get("llama") else "NON attivo (usa solo fallback)"
    print(f"  Server : online")
    print(f"  Llama  : {llama_stato}")
    print()

    stampa_lista_npc(NPC_PROFILES)
    print()
    scelta_npc = input("Scegli spirito con cui iniziare (invio = Levias): ").strip()
    if scelta_npc not in NPC_PROFILES:
        scelta_npc = "Levias"

    npc_corrente = scelta_npc
    profilo      = dict(NPC_PROFILES[npc_corrente])
    stampa_header_npc(npc_corrente, profilo, debug)

    while True:
        try:
            testo = input("Cavaliere: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Arrivederci.")
            break

        if not testo:
            continue

        # ------------------------------------------------------------------
        # Comandi
        # ------------------------------------------------------------------
        if testo == "exit":
            print("\n  Arrivederci.")
            break

        elif testo == "/status":
            print(f"\n  SPIRITO  : {npc_corrente}")
            print(f"  Ostilita : {barra(profilo['hostility'])} {profilo['hostility']}/100  [{umore(profilo['hostility'])}]")
            print(f"  Amicizia : {barra(profilo['friendship'])} {profilo['friendship']}/100")
            print(f"  Llama    : {llama_stato}")
            print()
            continue

        elif testo == "/npcs":
            stampa_lista_npc(NPC_PROFILES)
            continue

        elif testo.startswith("/npc "):
            nuovo = testo[5:].strip()
            if nuovo in NPC_PROFILES:
                npc_corrente = nuovo
                profilo      = dict(NPC_PROFILES[npc_corrente])
                stampa_header_npc(npc_corrente, profilo, debug)
            else:
                print(f"  Spirito '{nuovo}' non trovato. Usa /npcs per la lista.")
            continue

        elif testo == "/reset":
            post("/reset", {"npc_name": npc_corrente})
            profilo["hostility"]  = NPC_PROFILES[npc_corrente]["hostility"]
            profilo["friendship"] = NPC_PROFILES[npc_corrente]["friendship"]
            print(f"  Memoria e ostilita di {npc_corrente} resettate.")
            print()
            continue

        elif testo == "/resetall":
            post("/reset", {})
            print("  Tutti gli spiriti resettati.")
            print()
            continue

        elif testo == "/storia":
            data   = get(f"/history/{npc_corrente}")
            storia = data.get("history", [])
            if not storia:
                print(f"  Nessuna storia con {npc_corrente}.")
            else:
                print(f"\n  --- Storia con {npc_corrente} ---")
                for h in storia:
                    print(f"  Cavaliere  : {h.get('player', '')}")
                    print(f"  {npc_corrente:<11}: {h.get('npc', '')}")
                    print()
            continue

        elif testo == "/triggers":
            print("\n  Parole trigger per sbloccare Malakai:")
            for t in MALAKAI_TRIGGERS:
                print(f"    - {t}")
            print()
            continue

        elif testo.startswith("/debug"):
            parti = testo.split()
            if len(parti) > 1 and parti[1] == "on":
                debug = True
                print("  Debug attivato -- [AI]=llama.cpp  [FB]=fallback")
            else:
                debug = False
                print("  Debug disattivato.")
            continue

        # ------------------------------------------------------------------
        # Chiamata al server
        # ------------------------------------------------------------------
        result = post("/chat", {
            "player_input": testo,
            "npc_name":     npc_corrente,
            "hostility":    profilo["hostility"],
            "friendship":   profilo["friendship"],
        })

        if "error" in result:
            print(f"\n  [ERRORE] {result['error']}")
            print("  Verifica che 'python ai_server.py' sia ancora in esecuzione.")
            print()
            continue

        risposta   = result.get("response", "...")
        nuova_host = result.get("new_hostility", profilo["hostility"])
        source     = result.get("source", "?")
        intent     = result.get("intent", "?")
        sbloccato  = result.get("npc_unlocked", False)
        delta      = nuova_host - profilo["hostility"]

        print()
        tag = ("  " + icona_sorgente(source)) if debug else ""
        print(f"  {npc_corrente}: {risposta}{tag}")

        delta_str = f"(+{delta})" if delta > 0 else f"({delta})" if delta < 0 else "(=)"
        print(f"\n  Ostilita : {barra(nuova_host)} {nuova_host}/100  [{umore(nuova_host)}]  {delta_str}")

        if debug:
            print(f"  Debug    : sorgente={source}  intent={intent}")

        print()

        profilo["hostility"] = nuova_host

        # ------------------------------------------------------------------
        # Avvisi narrativi
        # ------------------------------------------------------------------
        if nuova_host >= 95:
            print(f"  [!] {npc_corrente} sta per attaccare. Scegli le prossime parole con cura.")
            print()

        if nuova_host <= 15 and profilo["friendship"] >= 20:
            print(f"  [*] Hai guadagnato la piena fiducia di {npc_corrente}!")
            print()

        if sbloccato:
            print(f"  [~] Malakai ha abbassato la guardia. E' il momento di parlare.")
            print()

        if npc_corrente == "Rigon" and nuova_host == 100:
            print(f"  [X] Rigon ha chiuso ogni dialogo. Non puoi piu parlargli.")
            print()


if __name__ == "__main__":
    main()