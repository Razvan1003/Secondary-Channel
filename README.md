# Secondary-Channel

Canal secundar de urgenta pentru o drona bazata pe MAVLink.

Acest repository contine scripturi Python separate, realizate pentru un
proiect de licenta. Scripturile sunt folosite pentru validarea incrementala a
unui canal secundar de siguranta in simulare, fara integrare hardware reala.

## Scop

Scopul proiectului este demonstratia unei logici simple pentru un canal
secundar de siguranta:

- monitorizare MAVLink
- detectie de evenimente critice
- activare a unei reactii de urgenta
- validare experimentala in ArduPilot SITL

## Versiuni incluse

- `secondary_channel_v1.py`
  - failover automat dupa pierderea heartbeat-ului
  - activare logica secundara
  - trimitere `RTL`
  - verificare `COMMAND_ACK`
- `secondary_channel_v2_1.py`
  - activare manuala a canalului secundar
  - mentinere a pozitiei si altitudinii curente
  - implementare prin `GUIDED hold` pe baza pozitiei curente
  - confirmare operationala in Mission Planner
- `secondary_channel_v2_2.py`
  - activare manuala a canalului secundar
  - trimitere comanda `LAND`
  - verificare `COMMAND_ACK`
  - confirmare operationala in Mission Planner
- `secondary_channel_v2_3.py`
  - activare manuala combinata
  - `GUIDED hold` prin tasta `h`
  - `LAND` prin tasta `d`
  - scenariu incremental hold apoi land
- `secondary_channel_v2_4.py`
  - failover automat configurabil
  - monitorizare heartbeat cu timeout de 5 secunde
  - reactie automata selectata din cod: `rtl`, `hold`, `land`
  - `HOLD` cu fallback pe ultima pozitie cunoscuta de pe monitor link
- `secondary_channel_v2_5.py`
  - failover automat cu selectie la runtime dupa pierderea linkului
  - meniul apare doar dupa `Primary link lost`
  - optiuni: `r = RTL`, `h = HOLD`, `l = LAND`
  - executie a reactiei alese fara editarea codului sursa

## Arhitectura de test

Scripturile au fost testate in simulare cu:

`ArduPilot SITL -> MAVProxy -> Mission Planner`

Endpoint-uri MAVLink folosite in test:

- `14550` pentru Mission Planner
- `14560` pentru scriptul Python al canalului secundar
- `5762` pentru conexiunea separata de comanda folosita in V1, V2.4 si V2.5

Aceste porturi sunt endpoint-uri software de simulare, nu canale RF reale.

## Cerinte

- Python 3
- `pymavlink`

Instalare:

```bash
pip install pymavlink
```

## Configurare

### V1

Configuratia implicita din `secondary_channel_v1.py` este:

```python
MONITOR_CONNECTION = "udpin:0.0.0.0:14560"
COMMAND_CONNECTION = "tcp:172.30.214.87:5762"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.2
COMMAND_ACK_TIMEOUT = 3
```

Configuratia a fost folosita intr-un setup in care MAVProxy ruleaza in WSL,
iar scriptul Python ruleaza pe Windows. Daca IP-ul din WSL se schimba, valoarea
`COMMAND_CONNECTION` trebuie actualizata.

### V2.1

Configuratia implicita din `secondary_channel_v2_1.py` este:

```python
MAVLINK_CONNECTION = "udpin:0.0.0.0:14560"
CHECK_INTERVAL = 0.2
HOLD_SEND_INTERVAL = 0.5
```

### V2.2

Configuratia implicita din `secondary_channel_v2_2.py` este:

```python
MAVLINK_CONNECTION = "udpin:0.0.0.0:14560"
CHECK_INTERVAL = 0.2
COMMAND_ACK_TIMEOUT = 3
```

### V2.3

Configuratia implicita din `secondary_channel_v2_3.py` este:

```python
MAVLINK_CONNECTION = "udpin:0.0.0.0:14560"
CHECK_INTERVAL = 0.2
HOLD_SEND_INTERVAL = 0.5
COMMAND_ACK_TIMEOUT = 3
```

### V2.4

Configuratia implicita din `secondary_channel_v2_4.py` este:

```python
MONITOR_CONNECTION = "udpin:0.0.0.0:14560"
COMMAND_CONNECTION = "tcp:172.30.214.87:5762"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.2
COMMAND_ACK_TIMEOUT = 3
HOLD_SEND_INTERVAL = 0.5
POSITION_CAPTURE_TIMEOUT = 1.0
EMERGENCY_ACTION = "land"
```

Reactia poate fi setata direct din cod la una dintre valorile:

- `rtl`
- `hold`
- `land`

### V2.5

Configuratia implicita din `secondary_channel_v2_5.py` este:

```python
MONITOR_CONNECTION = "udpin:0.0.0.0:14560"
COMMAND_CONNECTION = "tcp:172.30.214.87:5762"
HEARTBEAT_TIMEOUT = 5
CHECK_INTERVAL = 0.2
COMMAND_ACK_TIMEOUT = 3
HOLD_SEND_INTERVAL = 0.5
POSITION_CAPTURE_TIMEOUT = 1.0
```

In V2.5, reactia nu mai este fixata in cod. Alegerea se face dupa pierderea
heartbeat-ului, direct din consola:

- `r = RTL`
- `h = HOLD`
- `l = LAND`

## Rulare

Pornire V1:

```bash
python secondary_channel_v1.py
```

Pornire V2.1:

```bash
python secondary_channel_v2_1.py
```

Pornire V2.2:

```bash
python secondary_channel_v2_2.py
```

Pornire V2.3:

```bash
python secondary_channel_v2_3.py
```

Pornire V2.4:

```bash
python secondary_channel_v2_4.py
```

Pornire V2.5:

```bash
python secondary_channel_v2_5.py
```

Exemplu de pornire SITL:

```bash
sim_vehicle.py -v ArduCopter -f quad --map --console --out=172.30.208.1:14550 --out=172.30.208.1:14560
```

## Test rapid V1

1. Se porneste simularea ArduPilot SITL.
2. Se porneste Mission Planner pe `UDP 14550`.
3. Se porneste scriptul Python V1.
4. Vehiculul este trecut in `GUIDED`, armat si ridicat la 5 m.
5. In MAVProxy se elimina doar output-ul monitorizat de script:
   `output remove 172.30.208.1:14560`
6. Scriptul trebuie sa afiseze:
   - `Primary link lost`
   - `Secondary channel activated`
   - `RTL command sent. Waiting for COMMAND_ACK...`
   - `COMMAND_ACK received for RTL: MAV_RESULT_ACCEPTED`
7. Mission Planner trebuie sa indice trecerea in `RTL`.

## Test rapid V2.1

1. Se porneste simularea ArduPilot SITL.
2. Se porneste Mission Planner pe `UDP 14550`.
3. Se porneste scriptul `secondary_channel_v2_1.py`.
4. Vehiculul este trecut in `GUIDED`, armat si ridicat la 5 m.
5. In consola scriptului se apasa `h` sau `l`.
6. Scriptul trebuie sa afiseze:
   - `Manual secondary-channel activation requested`
   - `Sending GUIDED hold target based on current position...`
   - `GUIDED hold is active`
7. Mission Planner trebuie sa arate ca vehiculul ramane in `GUIDED`
   si mentine aproximativ pozitia si altitudinea curenta.

## Test rapid V2.2

1. Se porneste simularea ArduPilot SITL.
2. Se porneste Mission Planner pe `UDP 14550`.
3. Se porneste scriptul `secondary_channel_v2_2.py`.
4. Vehiculul este trecut in `GUIDED`, armat si ridicat la 5 m.
5. In consola scriptului se apasa `l` sau `d`.
6. Scriptul trebuie sa afiseze:
   - `Manual secondary-channel activation requested`
   - `Sending LAND command...`
   - `COMMAND_ACK received for LAND: MAV_RESULT_ACCEPTED`
7. Mission Planner trebuie sa arate trecerea in `LAND`
   si coborarea controlata spre sol.

## Test rapid V2.3

1. Se porneste simularea ArduPilot SITL.
2. Se porneste Mission Planner pe `UDP 14550`.
3. Se porneste scriptul `secondary_channel_v2_3.py`.
4. Vehiculul este trecut in `GUIDED`, armat si ridicat la 5 m.
5. In consola scriptului se apasa `h` pentru `GUIDED hold`.
6. Se verifica mentinerea pozitiei si a altitudinii curente.
7. In acelasi zbor, in consola scriptului se apasa `d` pentru `LAND`.
8. Scriptul trebuie sa afiseze:
   - activarea `GUIDED hold`
   - apoi `Sending LAND command...`
   - `COMMAND_ACK received for LAND: MAV_RESULT_ACCEPTED`
9. Mission Planner trebuie sa arate mai intai mentinerea in `GUIDED`,
   apoi trecerea in `LAND` si coborarea spre sol.

## Test rapid V2.4

1. Se porneste simularea ArduPilot SITL.
2. Se porneste Mission Planner pe `UDP 14550`.
3. Se porneste scriptul `secondary_channel_v2_4.py`.
4. In cod se seteaza `EMERGENCY_ACTION` la `rtl`, `hold` sau `land`.
5. Vehiculul este trecut in `GUIDED`, armat si ridicat la 5 m.
6. In MAVProxy se elimina output-ul monitorizat de script:
   `output remove 172.30.208.1:14560`
7. Scriptul trebuie sa afiseze:
   - `Primary link lost`
   - `Secondary channel activated`
   - apoi reactia configurata
8. Pentru `rtl` si `land`, validarea se face prin `COMMAND_ACK` si observarea
   modului in Mission Planner.
9. Pentru `hold`, validarea este operationala: vehiculul ramane in `GUIDED`
   si mentine aproximativ pozitia si altitudinea curenta.

## Test rapid V2.5

1. Se porneste simularea ArduPilot SITL.
2. Se porneste Mission Planner pe `UDP 14550`.
3. Se porneste scriptul `secondary_channel_v2_5.py`.
4. Vehiculul este trecut in `GUIDED`, armat si ridicat la 5 m.
5. In MAVProxy se elimina output-ul monitorizat de script:
   `output remove 172.30.208.1:14560`
6. Dupa timeout, scriptul trebuie sa afiseze:
   - `Primary link lost`
   - `Secondary channel activated`
   - meniul cu `r = RTL`, `h = HOLD`, `l = LAND`
7. Operatorul alege reactia direct in consola in acel moment.
8. Scriptul executa reactia aleasa:
   - `RTL` cu `COMMAND_ACK`
   - `LAND` cu `COMMAND_ACK`
   - `HOLD` prin `GUIDED hold`

## Limitari

V1 nu include:

- `LAND`
- `HOLD`
- comutare manuala
- telemetrie avansata
- GUI

V2.1 nu include:

- `LAND`
- selectie multipla de comenzi
- control complet roll/pitch/yaw
- telemetrie complexa
- hardware LoRa real

V2.2 nu include:

- selectie multipla de comenzi
- control complet roll/pitch/yaw
- telemetrie complexa
- hardware LoRa real

V2.3 nu include:

- selectie avansata de comenzi
- telemetrie complexa
- control complet roll/pitch/yaw
- hardware LoRa real

V2.4 nu include:

- selectie interactiva a reactiei
- GUI
- telemetrie complexa
- control complet roll/pitch/yaw
- hardware LoRa real

V2.5 nu include:

- GUI
- selectie grafica
- telemetrie complexa
- control complet roll/pitch/yaw
- hardware LoRa real

In V2.1, `GUIDED hold` este implementat cu mesaje
`SET_POSITION_TARGET_GLOBAL_INT`. Aceste mesaje nu intorc `COMMAND_ACK`, astfel
ca validarea este operationala: vehiculul trebuie sa ramana in `GUIDED` si sa
isi mentina aproximativ pozitia si altitudinea curenta.

In V2.2, `LAND` este implementat cu `MAV_CMD_NAV_LAND`, astfel incat validarea
se face atat prin `COMMAND_ACK`, cat si operational, prin observarea coborarii
si a aterizarii in Mission Planner.

In V2.3, aceeasi sesiune de test poate combina doua actiuni manuale:
mai intai `GUIDED hold`, apoi `LAND`.

## Rolul repository-ului

Acest repository are rol didactic si de validare experimentala:

- demonstreaza monitorizarea MAVLink dintr-un proces Python separat
- demonstreaza un failover automat de tip `RTL`
- demonstreaza o activare manuala de tip `GUIDED hold`
- demonstreaza o activare manuala de tip `LAND`
- demonstreaza un scenariu combinat `hold` urmat de `land`
- demonstreaza un failover automat configurabil prin `rtl`, `hold` sau `land`
- demonstreaza alegerea reactiei de urgenta dupa pierderea linkului, fara
  editarea codului sursa
- ofera o baza clara pentru etape viitoare mai complexe
