#!/bin/bash

PRG=$0
VERSION="TV P2P - Sopcast-Pi v2.0"
number_regex='^[0-9]+$'
DIR="$( cd "$( dirname "$0" )" && pwd )"

let i=0
while read line || [[ -n "${line}" ]]; do ((++i))
	[[ "$line" =~ ^#.*$ ]] && continue
    CANALES[$i]=`echo ${line} | cut -d ";" -f1`
	ENLACES[$i]=`echo ${line} | cut -d ";" -f2`
done < "${DIR}/canales.txt"

usage()
{
	echo "${VERSION}"
	echo ""
	echo "Uso: ${PRG} [OPCIONES]"
	echo ""
	echo "Opciones:"
	echo " -h			Muestra este menú"
	echo " -v			Muestra la versión"
	echo " -s			Apaga OMXPlayer y cierra la conexión con Sopcast"
	echo " -l			Lista de todos los canales preconfigurados"
	echo " -c [CANAL]		Indica el canal a cargar (ver formatos admitidos)"
	echo " -o			Apaga XBMC y ejecuta OMXPlayer"
	echo ""
	echo "Formatos admitidos para [CANAL]:"
	echo " - Enlace completo de Sopcast. Ejemplo: sop://broker.sopcast.com:3912/150577"
	echo " - Código de canal de uno de los canales preconfigurados (opción -l). Ejemplo: 1"
}

stop_playing()
{
	kill -9 $(pidof -x qemu-i386) > /dev/null 2>&1
	kill -2 $(pidof -x omxplayer.bin) > /dev/null 2>&1
	listening=1
	while [ -n "${listening}" ]; do
		listening=`netstat -na | grep 12345 | grep LISTEN | tail -1`
		sleep 1
	done
}

get_sopcast_link()
{
	wget $1 -O ${DIR}/page.html -o /dev/null
	sopcast_link_tmp=`grep "sop://" ${DIR}/page.html | tail -1 | awk 'BEGIN {FS="sop://"} {print $2}' | cut -d " " -f1`
	rm -f ${DIR}/page.html
	if ! [[ ${sopcast_link: -1} =~ ${number_regex} ]]; then
		sopcast_link_tmp=${sopcast_link_tmp%?}
	fi
	sopcast_link="sop://${sopcast_link_tmp}"
	echo "${sopcast_link}"
}

list_channels()
{
	printf "ID\tCanal\n"
	for i in "${!CANALES[@]}"; do 
		printf "%s\t%s\n" "$i" "${CANALES[$i]}"
	done
}

[[ $# -lt 1 ]] && usage && exit 1

while getopts ":hvsloc:" OPTION
do
	case "$OPTION" in
		h)
			usage
			exit 1
			;;
		v)
			echo "${VERSION}"
			exit 1
			;;
		s)
			stop_playing
			echo "Reproducción detenida"
			exit 1
			;;
		l)
			list_channels
			exit 1
			;;
		o)
			OMXPLAYER=1;
			;;
		c)
			CANAL=${OPTARG}
			;;
		?)
			usage
			exit 1
			;;
	esac
done

if [[ ${CANAL} == sop://broker.sopcast.com:3912/* ]]; then
	ENLACE=${CANAL}
	TEXTO="Cargando canal ${ENLACE}..."
	NOMBRE_CANAL=${CANAL}
elif [[ ${CANAL} =~ ${number_regex} ]] && [[ -n ${ENLACES[${CANAL}]} ]]; then
	if [[ ${ENLACES[${CANAL}]} == sop://broker.sopcast.com:3912/* ]]; then
		ENLACE=${ENLACES[${CANAL}]}
		TEXTO="Cargando canal ${CANALES[${CANAL}]} (${ENLACE})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
	elif [[ ${ENLACES[${CANAL}]} == http* ]]; then
		ENLACE=`get_sopcast_link ${ENLACES[${CANAL}]}`
		TEXTO="Cargando canal ${CANALES[${CANAL}]} (${ENLACE})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
	fi
else
	usage
	exit 1
fi

stop_playing
echo "${TEXTO}"
${DIR}/qemu-i386 ${DIR}/lib/ld-linux.so.2 --library-path ${DIR}/lib ${DIR}/sp-sc-auth ${ENLACE} 1234 12345 > /dev/null 2>&1 &

let timeout=0
while [ ${timeout} -lt 30 ]; do ((++i))
	listening=`netstat -na | grep 12345 | grep LISTEN | tail -1`
	process=`ps aux | grep qemu-i386 | grep -v grep`
	if [ -n "${listening}" ] || [ -z "${process}" ]; then
		break
	else
		sleep 1
	fi
done

if [ -z "${listening}" ]; then
	echo "Imposible conectar al canal especificado"
	stop_playing
	exit 1
else
	echo "Conectado al canal ${NOMBRE_CANAL}"
fi

if [[ ${OMXPLAYER} -eq 1 ]]; then
	if ps ax | grep -v grep | grep xbmc > /dev/null; then
		echo "Apagando XBMC..."
		/etc/init.d/xbmc stop
	fi
	echo "Encendiendo OMXPlayer..."
	omxplayer -r http://127.0.0.1:12345 > /dev/null 2>&1 &
fi

exit 0
