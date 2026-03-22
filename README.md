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

## Arhitectura de test

Scripturile au fost testate in simulare cu:

`ArduPilot SITL -> MAVProxy -> Mission Planner`

Endpoint-uri MAVLink folosite in test:

- `14550` pentru Mission Planner
- `14560` pentru scriptul Python al canalului secundar
- `5762` pentru conexiunea separata de comanda folosita in V1

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

## Rulare

Pornire V1:

```bash
python secondary_channel_v1.py
```

Pornire V2.1:

```bash
python secondary_channel_v2_1.py
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

In V2.1, `GUIDED hold` este implementat cu mesaje
`SET_POSITION_TARGET_GLOBAL_INT`. Aceste mesaje nu intorc `COMMAND_ACK`, astfel
ca validarea este operationala: vehiculul trebuie sa ramana in `GUIDED` si sa
isi mentina aproximativ pozitia si altitudinea curenta.

## Rolul repository-ului

Acest repository are rol didactic si de validare experimentala:

- demonstreaza monitorizarea MAVLink dintr-un proces Python separat
- demonstreaza un failover automat de tip `RTL`
- demonstreaza o activare manuala de tip `GUIDED hold`
- ofera o baza clara pentru etape viitoare mai complexe
