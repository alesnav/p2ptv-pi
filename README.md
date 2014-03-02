## sopcast-pi

Sopcast para Raspberry Pi basado en [este cliente Sopcast para Linux](https://code.google.com/p/sopcast-player/downloads/list) y utilizando qemu-i386.

Gracias a [tayoken](http://www.raspberrypi.org/phpBB3/memberlist.php?mode=viewprofile&u=72614) por recompilar qemu-i386 y [compartirlo](http://www.raspberrypi.org/phpBB3/viewtopic.php?t=46342).

Gracias a [somosbinarios.es](http://www.somosbinarios.es) por realizar el desarrollo de la idea de la que parte este código. Se puede acceder a la versión 1.1 mediante [este enlace](http://www.somosbinarios.es/raspberry-pi-television-y-futbol-en-un-click-v1-1/).

### Script para reproducción automática `tv.sh`

En este momento, únicamente se ha probado su utilización sobre raspbian, por lo que quizás surja algún problema usando cualquier otra distribución. Si esto sucediera, abriendo un ticket desde [aquí](https://github.com/alesnav/sopcast-pi/issues) se podría adaptar el código para su correcto funcionamiento en todas las plataformas.

#### Uso del script
    $ ./tv.sh [OPCIONES]

#### Opciones
* **-h** - Muestra este menú
* **-v** - Muestra la versión
* **-s** - Apaga OMXPlayer y cierra la conexión con Sopcast
* **-l** - Lista de todos los canales preconfigurados
* **-c [CANAL]** - Indica el canal a cargar (ver formatos admitidos)
* **-o** - Apaga XBMC y ejecuta OMXPlayer

#### Formatos admitidos para [CANAL]
* Código de canal de uno de los canales preconfigurados (opción -l). Ejemplo: `./tv.sh -c 1`
* Enlace completo de Sopcast. Ejemplo: `./tv.sh -c sop://broker.sopcast.com:3912/150577`

#### Requisitos
* Si iptables está activo, deberá permitir la conexión al puerto 12345 de 127.0.0.1 (localhost) para la reproducción de los canales Sopcast.
* Tener OMXPlayer instalado. Se puede instalar ejecutando `sudo apt-get install omxplayer`
* Si xbmc está instalado, deberá existir un script de arranque y parada para que sea posible parar xbmc y arrancar OMXPlayer. Concretamente, el script deberá quedar en `/etc/init.d/xbmc`.

### Lista de canales preconfigurados `canales.txt`
Este fichero contiene toda la lista de canales preconfigurados, que de momento coincide con los once canales de [ArenaVision](http://www.arenavision.in/).

Es posible introducir nuevos canales con el siguiente formato: `<NOMBRE_CANAL>;<ENLACE_SOPCAST>`

Los canales de ArenaVision, sin embargo, están asociados a una dirección HTTP ya que el código de canal no siempre se mantiene y es necesario comprobarlo al vuelo antes de realizar la conexión.
