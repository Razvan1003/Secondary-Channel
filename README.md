# Secondary-Channel

Canal secundar de urgenta pentru o drona bazata pe MAVLink.

Acest repository contine **Versiunea 1 (V1)** a unui script Python separat,
realizat pentru un proiect de licenta. Scriptul nu este integrat in Mission
Planner si nu inlocuieste canalul principal. Rolul lui este sa functioneze ca
un mecanism simplu de monitorizare si reactie de urgenta.

## Scop

Scopul proiectului este demonstratia unei logici de baza pentru un canal
secundar de siguranta:

- conectare la un flux MAVLink
- monitorizare a mesajelor `HEARTBEAT`
- detectare a pierderii fluxului dupa un timeout de 5 secunde
- afisare de mesaje clare in consola
- trimitere automata a unei comenzi `RTL` (`Return To Launch`)

## Ce face V1

Versiunea 1 implementeaza strict logica minima de baza:

- se conecteaza la un flux MAVLink folosind `pymavlink`
- asteapta primul `HEARTBEAT`
- memoreaza momentul ultimului heartbeat primit
- afiseaza in consola heartbeat-urile primite normal
- considera canalul pierdut daca nu mai primeste heartbeat timp de 5 secunde
- afiseaza mesajele:
  - `Primary link lost`
  - `Secondary channel activated`
- trimite o singura data comanda `RTL` pentru fiecare eveniment de pierdere

## Arhitectura de test folosita

Scriptul a fost testat in simulare cu urmatoarea arhitectura:

`ArduPilot SITL -> MAVProxy -> Mission Planner`

In paralel cu Mission Planner, scriptul primeste un flux MAVLink separat prin
un al doilea `--out` configurat in MAVProxy.

Exemplu de configurare folosita:

- `14550` pentru Mission Planner
- `14560` pentru scriptul Python

## Fisierul principal

- `secondary_channel_v1.py`

## Cerinte

- Python 3
- `pymavlink`

Instalare dependinta:

```bash
pip install pymavlink
```

## Configurare

In script exista cateva constante usor de modificat:

- `MAVLINK_CONNECTION`
- `HEARTBEAT_TIMEOUT`
- `CHECK_INTERVAL`

Configuratia implicita din V1 este:

```python
MAVLINK_CONNECTION = "udpin:0.0.0.0:14560"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.5
```

Aceasta configuratie a fost aleasa pentru un setup in care MAVProxy ruleaza in
WSL, iar scriptul Python ruleaza pe Windows.

## Rulare

Pornire script:

```bash
python secondary_channel_v1.py
```

Exemplu de pornire a simularii cu doua iesiri MAVLink:

```bash
sim_vehicle.py -v ArduCopter -f quad --map --console --out=127.0.0.1:14550 --out=127.0.0.1:14560
```

Sau, pentru unele configuratii WSL -> Windows:

```bash
sim_vehicle.py -v ArduCopter -f quad --map --console --out=172.30.208.1:14550 --out=172.30.208.1:14560
```

## Test rapid

1. Se porneste simularea ArduPilot SITL.
2. Se porneste Mission Planner pe `UDP 14550`.
3. Se porneste scriptul Python pentru canalul secundar.
4. Scriptul trebuie sa afiseze heartbeat-urile primite normal.
5. La intreruperea fluxului de heartbeat pentru mai mult de 5 secunde,
   scriptul afiseaza pierderea canalului si trimite `RTL`.

## Limitari V1

Aceasta versiune este intentionat simpla si nu include:

- `LAND`
- `HOLD`
- comutare manuala
- interfata grafica
- telemetrie inapoi
- logica avansata pentru mai multe tipuri de esec

In plus, V1 detecteaza pierderea heartbeat-ului pe fluxul monitorizat. Daca
sursa este oprita complet, comanda `RTL` este demonstrata logic la nivel de
script, dar vehiculul poate sa nu mai fie disponibil pentru executia ei.

## Rolul versiunii V1

Aceasta versiune are rol didactic si de validare experimentala:

- demonstreaza ca un proces Python separat poate monitoriza MAVLink
- demonstreaza detectia unui timeout de heartbeat
- demonstreaza activarea unei reactii automate de urgenta
- ofera o baza clara pentru versiuni ulterioare mai complexe
