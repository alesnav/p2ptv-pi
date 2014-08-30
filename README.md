## p2ptv-pi

P2P TV (Sopcast & AceStream) para Raspberry Pi.

Cliente Sopcast basado en [este cliente Sopcast para Linux](https://code.google.com/p/sopcast-player/downloads/list) y utilizando qemu-i386. Gracias a [tayoken](http://www.raspberrypi.org/phpBB3/memberlist.php?mode=viewprofile&u=72614) por recompilar qemu-i386 y [compartirlo](http://www.raspberrypi.org/phpBB3/viewtopic.php?t=46342).

Cliente AceStream realizado por [tarasian666](https://github.com/tarasian666/) y accesible mediante el [repositorio Github](https://github.com/tarasian666/acestream).

Gracias a [somosbinarios.es](http://www.somosbinarios.es) por realizar el desarrollo de la idea de la que parte este código. Se puede acceder a la versión 1.1 mediante [este enlace](http://www.somosbinarios.es/raspberry-pi-television-y-futbol-en-un-click-v1-1/).

### Script para reproducción automática `tv.sh`

En este momento, únicamente se ha probado su utilización sobre raspbian, por lo que quizás surja algún problema usando cualquier otra distribución. Si esto sucediera, abriendo un ticket desde [aquí](https://github.com/alesnav/p2ptv-pi/issues) se podría adaptar el código para su correcto funcionamiento en todas las plataformas.

#### Uso del script
    $ ./tv.sh [OPCIONES]

#### Opciones
* **-h** - Muestra este menú
* **-V** - Muestra la versión
* **-v** - Activa el modo debug
* **-s [0|1]** - Apaga OMXPlayer y cierra la conexión P2P TV. 0: No iniciar XBMC. 1: Iniciar XBMC
* **-t [n]** - Indica el tiempo en segundos a esperar para la carga del canal antes de iniciar OMXPlayer (15 por defecto).
* **-l** - Lista de todos los canales preconfigurados
* **-p [n]** - Muestra la programación de ArenaVision para el dia indicado. [n] indica el día de la prohramación, siendo 0 el día actual, 1 el día siguiente, etc.
* **-c [CANAL]** - Indica el canal a cargar (ver formatos admitidos)
* **-o [0|1]** - Apaga XBMC e inicia OMXPlayer. 0: Salida de video por defecto. 1: Salida por HDMI.

#### Formatos admitidos para [CANAL]
* Código de canal de uno de los canales preconfigurados (opción -l). Ejemplo: `./tv.sh -c 1`
* Enlace completo de Sopcast. Ejemplo: `./tv.sh -c sop://broker.sopcast.com:3912/123456`
* Enlace completo de AceStream (hash). Ejemplo: `./tv.sh -c acestream://ff6d068d982f5ac218d164cf43f97dc39926cf55`
* Enlace completo de AceStream (*.acelive). Ejemplo: `./tv.sh -c http://example.com/tv.acelive`

#### Requisitos
* Si iptables está activo, deberá permitir la conexión al puerto 6878 de 127.0.0.1 (localhost) para la reproducción de los canales P2P.
* Tener OMXPlayer y wget instalados. Se pueden instalar ejecutando `sudo apt-get install omxplayer wget`
* Si XBMC está instalado, deberá contar con un script de arranque y parada. Por defecto, se usa el método de Debian (service xbmc start|restart|stop). Si el método es diferente, se deberá editar el script `tv.sh`.

### Lista de canales preconfigurados `canales.txt`
Este fichero contiene toda la lista de canales preconfigurados.

Es posible introducir nuevos canales con el siguiente formato: `<Sopcast|AceStream>;<NOMBRE_CANAL>;<ENLACE>`

Los canales existentes, sin embargo, están asociados a una dirección HTTP ya que el código de canal no siempre se mantiene y es necesario comprobarlo al vuelo antes de realizar la conexión.

La lista completa se puede consultar ejecutando `./tv.sh -l`. Igualmente, la lista actual es la siguiente:

    ID    Canal
    1     ArenaVision 1
    2     ArenaVision 2
    3     ArenaVision 3
    4     ArenaVision 4
    5     ArenaVision 5
    6     ArenaVision 6
    7     ArenaVision 7
    8     ArenaVision 8
    9     ArenaVision 9
    10    ArenaVision 10

### Instalación
    git clone https://github.com/alesnav/p2ptv-pi.git

### Ejemplo de uso
Ejemplo de reproducción del canal ArenaVision 5 iniciando automáticamente OMXPlayer: `./tv.sh -c 5 -o 1`

### Licencia
Este proyecto queda protegido bajo la licencia MIT.
