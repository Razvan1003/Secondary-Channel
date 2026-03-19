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

Versiunea 1 implementeaza logica de urgenta validata in simulare:

- monitorizeaza `HEARTBEAT` pe o conexiune dedicata
- considera linkul pierdut dupa 5 secunde fara heartbeat
- activeaza failover-ul logic prin mesajul `Secondary channel activated`
- trimite comanda `RTL`
- asteapta `COMMAND_ACK` pentru `RTL`
- ramane in stare de urgenta pana la reset manual

## Arhitectura de test folosita

Scriptul a fost testat in simulare cu urmatoarea arhitectura:

`ArduPilot SITL -> MAVProxy -> Mission Planner`

In paralel cu Mission Planner, scriptul primeste un flux MAVLink separat prin
un al doilea `--out` configurat in MAVProxy.

Exemplu de configurare folosita:

- `14550` pentru Mission Planner
- `14560` pentru monitorizarea heartbeat-ului in script
- `5762` pentru conexiunea separata de comanda folosita de script

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

- `MONITOR_CONNECTION`
- `COMMAND_CONNECTION`
- `HEARTBEAT_TIMEOUT`
- `CHECK_INTERVAL`
- `COMMAND_ACK_TIMEOUT`

Configuratia implicita din V1 este:

```python
MONITOR_CONNECTION = "udpin:0.0.0.0:14560"
COMMAND_CONNECTION = "tcp:172.30.214.87:5762"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.2
COMMAND_ACK_TIMEOUT = 3
```

Aceasta configuratie a fost folosita pentru un setup in care MAVProxy ruleaza
in WSL, iar scriptul Python ruleaza pe Windows. Daca IP-ul din WSL se schimba,
valoarea `COMMAND_CONNECTION` trebuie actualizata.

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
3. Se porneste scriptul Python.
4. Vehiculul este trecut in `GUIDED`, armat si ridicat la 5 m.
5. In MAVProxy se elimina doar output-ul monitorizat de script:
   `output remove 172.30.208.1:14560`
6. Scriptul trebuie sa afiseze:
   - `Primary link lost`
   - `Secondary channel activated`
   - `RTL command sent. Waiting for COMMAND_ACK...`
   - `COMMAND_ACK received for RTL: MAV_RESULT_ACCEPTED`
7. Mission Planner trebuie sa indice trecerea in `RTL`.

## Limitari V1

Aceasta versiune este intentionat simpla si nu include:

- `LAND`
- `HOLD`
- comutare manuala
- interfata grafica
- telemetrie inapoi
- logica avansata pentru mai multe tipuri de esec

In plus, V1 foloseste o conexiune separata pentru trimiterea comenzii `RTL`,
astfel incat failover-ul sa poata fi validat cu `COMMAND_ACK` chiar daca fluxul
de heartbeat monitorizat este intrerupt.

## Rolul versiunii V1

Aceasta versiune are rol didactic si de validare experimentala:

- demonstreaza ca un proces Python separat poate monitoriza MAVLink
- demonstreaza detectia unui timeout de heartbeat
- demonstreaza activarea unei reactii automate de urgenta
- demonstreaza confirmarea comenzii critice prin `COMMAND_ACK`
- ofera o baza clara pentru versiuni ulterioare mai complexe
