#  mkt2fgt

Convierte bloques de configuración de archivos .rsc de Mikrotik a su contraparte en FortiGate

## Línea de comando

### --mikrotik-config `ARCHIVO.RSC`

Archivo con la configuración del Mikrotik, formato tipo `/export`. No es necesario que esté toda la configuración, solo lo relevante para la conversión que se va a hacer. Por ejemplo, si solo se van a convertir los usuarios de ppp, con la sección `/ppp/secret` alcanza.

### --fortigate-config `ARCHIVO.CONF`

Archivo donde se escribirá el script de FortiOS.

### --ppp-users

Convierte la sección usuarios de PPP a usuarios locales de FortiGate (*config user local*).

### --map-interfaces `MKT_IF:FGT_IF ...`

Cambiar las referencias de las interfaces de Mikrotik `MKT_IF` a interfaces de FortiGate `FGT_IF`. Es **case insensitive** para la interfaz de Mikrotik, y **sensitive** para las de FortiGate.

#### Ejemplo

- --map-interfaces ether1:internal ether2:wan1 ether3:wan2

### --addresses `{INTERFACE ...|*}`

Genera el bloque de configuración para direcciones IPs de las interfaces (*config system interface*). Solo se migran las direcciones habilitadas.
Usar "*" para migrar todas las interfaces.

**IMPORTANTE**: en Mikrotik no existe el concepto de dirección primaria y secundaria. El script las convertirá en el orden que las encuentre y solo usará como primaria la primera que encuentre. Posiblemente requiera retoques manuales.

#### Ejemplo

- --addresses *
- --addresses ether1 ether2 ether4

### --dhcp-servers `{SERVER ...|*}`

Listado de **DHCP servers y leases** a migrar.
Usar "*" para migrar todos los DHCP servers. Solo se migrarán aquellos que estén habilitados.

#### Ejemplos

- --dhcp-servers LAN1 LAN2
- --dhcp-servers *