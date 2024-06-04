# dstnat2tf (documentación provisoria)


Generador de plantillas de Terraform a partir de archivos CSV o dumps de IPtables.

## Funcionamiento

Este conversor toma archivos con configuraciones -o CSV- y genera:

- Plantilla de Terraform, en dos archivos:
  - `output-basename`.`tf`: contiene virtual IPs y Policies.
  - `output-basename-services`.`tf`: contiene servicios *custom*: los que no vienen ya definidos en una configuración por default de  FortiGate (ej.: HTTP, DNS).
- Archivo `output-basename`.`xlsx`, una planilla de cálculo con el listado de reglas de DSTNAT.

### Interfaces

En muchos casos las reglas de DSTNAT no tienen interface de entrada -WAN- y, muchas veces, no hay información sobre la interface de salida -LAN, DMZ, etc.-, esto se puede compensar con estas opciones:

- `--map-network`: Se usa para identificar la interface -interna o externa- a partir de una IP o rango IP. Esta identificación se usa luego en virtual IPs y policies. Por ejemplo, `--map-network 181.229.177.143:wan1` y `--map-network 192.168.10.0/24:lan-legacy` setea la interface **wan1** en cada virtual IP o policy que ve a **IP 181.229.177.143**, y **lan-legacy** para las policies que mencionan una IP el **rango 192.168.10.0/24**.
- `--map-interface`: Usada cuando se sabe la interface, simplemente le setea el nombre que tendrá en el FortiGate. Por ejemplo, `--map-interface eth0:wan1` usa wan1 en la plantilla de FortiGate donde se menciona eth0 en las reglas.
- `--default-external`: Nombre de interface a usar cuando no pueda identificarse la WAN. También puede ser útil si hay una sola WAN y no quiere usarse `--map-network` y/o `--map-interface`.
- `--default-internal`: Idem anterior, pero para cuando no se puede identificar la LAN.

## Línea de comando

| opción | default | requerido |  descripción |
| --- | --- | :-: | --- |
| `--input` | | ✅ | Archivo CSV o dump de IPTables | 
| `--input-format`| | ✅ | Formato del archivo: `iptables` o `csv` |
| `--output-basename` | | ✅ | Prefijo del nombre de los archivos de salida (ej.: `cliente` generaría `cliente-services.tf` y `cliente.tf` |
| `--map-network` | | | `RED FORMATO CIDR`:`INTERFACE`, mapea la dirección de red a una interface (ej.: `181.229.177.143/29:wan1`)
| `--map-interface` | | | `INTERFACE ORIGINAL`:`INTERFACE FORTIGATE` mapea un nombre de una interface a un nuevo nombre en el FortiGate (ej.: `eth0:wan1`) |
| `--default-internal` | | | Nombre por default de la interface interna |
| `--default-external` | | | Nombre por default de la interface WAN |
| `--ignore-issues` | | | Generar el archivo de Terraform aunque haya reglas con problemas |
| `--use-sdwan` | | | Usar zonas SD-WAN en las policies | 
| `--sdwan-zone` | `virtual-wan-link` | | Zona SD-WAN para Internet |

## Formatos

### IPtables

Toma un archivo generado con iptables-save.

Los campos necesarios son:

| campo | requerido | default | descripcion |
| --- | --- | --- | --- |
| `-d` | ✅ | | IP externa (WAN) |
| `--dport` | ✅ | | Puerto Externo |
| `-p` | ✅ | | Protocolo |
| `--to-destination` | ✅ | | IP:PUERTO interno |

### CSV

Los campos necesarios son:

| campo | requerido | default | descripcion |
| --- | --- | --- | --- |
| `extip` | ✅ | | IP externa (WAN) |
| `protocol` | ✅ | | Protocolo |
| `extport` | ✅ | | Puerto externo |
| `mappedip` | ✅ | | IP Interna Destino (LAN, DMZ) |
| `mappedport` | | `extport` | Puerto interno |
| `comment` | | | Comentario/Descripción de la policy. |


