
#!/bin/bash

PRG=$0
VERSION="p2ptv-pi v3.0"
DIR="$( cd "$( dirname "$0" )" && pwd )"

xbmc_start="sudo service xbmc start"
xbmc_stop="sudo service xbmc stop"
xbmc_start="sudo service xbmc restart"

let i=0
while read line || [[ -n "${line}" ]]; do ((++i))
	[[ "$line" =~ ^#.*$ ]] && continue
	TIPOS_CANAL[$i]=`echo ${line} | cut -d ";" -f1 | tr 'a-z' 'A-Z'`
	CANALES[$i]=`echo ${line} | cut -d ";" -f2`
	ENLACES[$i]=`echo ${line} | cut -d ";" -f3`
done < "${DIR}/canales.txt"
usage()
{
	echo "${VERSION}"
	echo ""
	echo "Uso: ${PRG} [OPCIONES]"
	echo ""
	echo "Opciones:"
	echo " -h			Muestra este menú."
	echo " -v			Muestra la versión."
	echo " -s [0|1]		Apaga OMXPlayer y cierra la conexión P2P TV. 0: No iniciar XBMC. 1: Iniciar XBMC."
	echo " -l			Lista de todos los canales preconfigurados."
	echo " -c [CANAL]		Indica el canal a cargar (ver formatos admitidos)."
	echo " -o [0|1]		Apaga XBMC e inicia OMXPlayer. 0: Salida de video por defecto. 1: Salida por HDMI."
	echo " -t [n]			Indica el tiempo en segundos a esperar para la carga del canal antes de iniciar OMXPlayer (15 por defecto)."
	echo ""
	echo "Formatos admitidos para [CANAL]:"
	echo " - Código de canal de uno de los canales preconfigurados (opción -l). Ejemplo: ./tv.sh -c 1"
        echo " - Enlace completo de Sopcast. Ejemplo: ./tv.sh -c sop://broker.sopcast.com:3912/150577"
        echo " - Enlace completo de AceStream. Ejemplo: ./tv.sh -c acestream://ff6d068d982f5ac218d164cf43f97dc39926cf55"
}

stop_playing()
{
	if [[ -f ${DIR}/p2ptv-pi.pid ]]; then
		kill -9 $(cat ${DIR}/p2ptv-pi.pid) > /dev/null 2>&1
		rm -f ${DIR}/p2ptv-pi.pid
		echo "Reproducción detenida"
	fi
	kill -2 $(pidof -x omxplayer.bin) > /dev/null 2>&1
	listening=1
	while [ -n "${listening}" ]; do
		listening=`netstat -na | grep 6878 | grep LISTEN | tail -1`
		sleep 1
	done
	if [[ ${XBMC} -eq 1 ]]; then
		if ps ax | grep -v grep | grep xbmc > /dev/null; then
			echo "Reiniciando XBMC..."
			${xbmc_restart}
		else
			echo "Iniciando XBMC..."
			${xbmc_start}
		fi
	fi
}

get_sopcast_link()
{
	url_tmp=$1
	sopcast_link_tmp=`wget ${url_tmp} -O - ${DIR}/page.html -o /dev/null | grep "sop://" | tail -1 | awk 'BEGIN {FS="sop://"} {print $2}' | cut -d " " -f1`
	if ! [[ ${sopcast_link: -1} =~ ^[0-9]+$ ]]; then
		sopcast_link_tmp=${sopcast_link_tmp%?}
	fi
	sopcast_link="sop://${sopcast_link_tmp}"
	echo "${sopcast_link}"
}

get_acestream_link()
{
	url_tmp=$1
	acestream_link_tmp=`wget ${url_tmp} -O - -o /dev/null | grep "this.loadPlayer" | cut -d '"' -f2`
	acestream_link="acestream://${acestream_link_tmp}"
	if [[ "${acestream_link}" == "acestream://" ]]; then
		acestream_link=`wget ${url_tmp} -O - -o /dev/null | grep "this.loadTorrent" | cut -d '"' -f2`
	fi
	echo "${acestream_link}"
}

list_channels()
{
	printf "ID\tCanal\n"
	for i in "${!CANALES[@]}"; do
		printf "%s\t%s\n" "$i" "${CANALES[$i]} (${TIPOS_CANAL[$i]})"
	done
}

[[ $# -lt 1 ]] && usage && exit 1

while getopts ":hVvt:s:lo:c:" OPTION
do
	case "$OPTION" in
		h)
			usage
			exit 1
			;;
		V)
			echo "${VERSION}"
			exit 1
			;;
		v)
			VERBOSE=1
			;;

		t)
			re='^[0-9]+$'
			if ! [[ ${OPTARG} =~ ${re} ]] ; then
				usage
				exit 1
			else
				WAIT="${OPTARG}"
			fi
			;;
		s)
			if [ "${OPTARG}" == "1" ]; then
				XBMC=1
			else
				XBMC=0
			fi
			stop_playing
			exit 1
			;;
		l)
			list_channels
			exit 1
			;;
		o)
			OMXPLAYER=1;
			if [ "${OPTARG}" == "1" ]; then
				OMX_HDMI=1
			else
				OMX_HDMI=0
			fi
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

if [[ ${CANAL} == sop://* ]]; then
	ENLACE_P2P=${CANAL}
	ENLACE_OMXPLAYER="http://127.0.0.1:6878"
	TEXTO="Cargando canal Sopcast ${ENLACE_P2P}..."
	NOMBRE_CANAL=${CANAL}
	TIPO_CANAL="SOPCAST"
elif [[ ${CANAL} == acestream://* ]]; then
	ENLACE_P2P=${CANAL}
	ENLACE_OMXPLAYER=`echo ${ENLACE_P2P} | awk 'BEGIN {FS="acestream://"} {print "http://127.0.0.1:6878/LOAD/PID="$2}'`
	TEXTO="Cargando canal AceStream ${ENLACE_P2P}..."
	NOMBRE_CANAL=${CANAL}
	TIPO_CANAL="ACESTREAM"
elif [[ ${CANAL} =~ ^[0-9]+$ ]] && [[ -n ${ENLACES[${CANAL}]} ]] && [[ "${TIPOS_CANAL[${CANAL}]}" == "SOPCAST" ]]; then
	if [[ ${ENLACES[${CANAL}]} == sop://* ]]; then
		ENLACE_P2P=${ENLACES[${CANAL}]}
		ENLACE_OMXPLAYER="http://127.0.0.1:6878"
		TEXTO="Cargando canal Sopcast ${CANALES[${CANAL}]} (${ENLACE_P2P})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
		TIPO_CANAL="SOPCAST"
	elif [[ ${ENLACES[${CANAL}]} == http* ]]; then
		ENLACE_P2P=`get_sopcast_link ${ENLACES[${CANAL}]}`
		ENLACE_OMXPLAYER="http://127.0.0.1:6878"
		TEXTO="Cargando canal Sopcast ${CANALES[${CANAL}]} (${ENLACE_P2P})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
		TIPO_CANAL="SOPCAST"
	fi
elif [[ ${CANAL} =~ ^[0-9]+$ ]] && [[ -n ${ENLACES[${CANAL}]} ]] && [[ "${TIPOS_CANAL[${CANAL}]}" == "ACESTREAM" ]]; then
	if [[ ${ENLACES[${CANAL}]} == acestream://* ]]; then
		ENLACE_P2P=${ENLACES[${CANAL}]}
		ENLACE_OMXPLAYER=`echo ${ENLACE_P2P} | awk 'BEGIN {FS="acestream://"} {print "http://127.0.0.1:6878/LOAD/PID="$2}'`
		TEXTO="Cargando canal AceStream ${CANALES[${CANAL}]} (${ENLACE_P2P})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
		TIPO_CANAL="ACESTREAM"
	elif [[ ${ENLACES[${CANAL}]} == http* ]]; then
		ENLACE_P2P=`get_acestream_link ${ENLACES[${CANAL}]}`
		if [[ ${ENLACE_P2P} == acestream://* ]]; then
			ENLACE_OMXPLAYER=`echo ${ENLACE_P2P} | awk 'BEGIN {FS="acestream://"} {print "http://127.0.0.1:6878/LOAD/PID="$2}'`
		elif [[ ${ENLACE_P2P} == http* ]]; then
			ENLACE_OMXPLAYER="http://127.0.0.1:6878/LOAD/TORRENT=${ENLACE_P2P}"
		fi
		TEXTO="Cargando canal AceStream ${CANALES[${CANAL}]} (${ENLACE_P2P})..."
		NOMBRE_CANAL=${CANALES[${CANAL}]}
		TIPO_CANAL="ACESTREAM"
	fi
elif [[ ${CANAL} =~ ^https?://.*\.acelive$ ]]; then
	ENLACE_P2P=${CANAL}
	ENLACE_OMXPLAYER="http://127.0.0.1:6878/LOAD/TORRENT=${CANAL}"
	TEXTO="Cargando canal AceStream ${CANAL}..."
	NOMBRE_CANAL=${CANAL}
	TIPO_CANAL="ACESTREAM"
else
	usage
	exit 1
fi

stop_playing
echo "${TEXTO}"
if [[ "${TIPO_CANAL}" == "SOPCAST" ]]; then
	if [[ ${VERBOSE} -eq 1 ]];then
		echo "Comando: nice -10 ${DIR}/sopcast/qemu-i386 ${DIR}/sopcast/lib/ld-linux.so.2 --library-path ${DIR}/sopcast/lib ${DIR}/sopcast/sp-sc-auth ${ENLACE_P2P} 1234 6878 > /dev/null 2>&1 & echo $! > ${DIR}/p2ptv-pi.pid"
	fi
	nice -10 ${DIR}/sopcast/qemu-i386 ${DIR}/sopcast/lib/ld-linux.so.2 --library-path ${DIR}/sopcast/lib ${DIR}/sopcast/sp-sc-auth ${ENLACE_P2P} 1234 6878 > /dev/null 2>&1 & echo $! > ${DIR}/p2ptv-pi.pid
elif [[ "${TIPO_CANAL}" == "ACESTREAM" ]]; then
	if [[ ${VERBOSE} -eq 1 ]];then
		echo "Comando: nice -10 ${DIR}/acestream/start.py > /dev/null 2>&1 & echo $! > ${DIR}/p2ptv-pi.pid"
	fi
	nice -10 ${DIR}/acestream/start.py > /dev/null 2>&1 & echo $! > ${DIR}/p2ptv-pi.pid
	sleep 10
fi

let timeout=0
while [ ${timeout} -lt 60 ]; do ((++i))
	listening=`netstat -na | grep 6878 | grep LISTEN | tail -1`
	if [[ "${TIPO_CANAL}" == "SOPCAST" ]]; then
		process=`ps aux | grep qemu-i386 | grep -v grep`
	elif [[ "${TIPO_CANAL}" == "ACESTREAM" ]]; then
		process=`ps aux | grep "acestream/start.py" | grep -v grep`
	fi
	if [ -n "${listening}" ]; then
		if [[ ${VERBOSE} -eq 1 ]];then
			echo "El puerto de ${TIPO_CANAL} (6878) ya está la escucha."
		fi
		break
	elif [ -z "${process}" ]; then
		if [[ ${VERBOSE} -eq 1 ]];then
			echo "El proceso ${TIPO_CANAL} ya no existe."
		fi
		echo "Imposible conectar al canal especificado"
		stop_playing
		exit 1
	else
		if [[ ${VERBOSE} -eq 1 ]];then
			echo "Esperando 2 segundos a que el puerto 6878 esté a la escucha..."
		fi
		sleep 2
	fi
done

echo "Conectado al canal ${NOMBRE_CANAL} (${TIPO_CANAL})"

if [[ ${OMXPLAYER} -eq 1 ]]; then
	if ps ax | grep -v grep | grep xbmc > /dev/null; then
		echo "Apagando XBMC..."
		${xbmc_stop}
	fi
	if [[ -z ${WAIT} ]]; then
		WAIT=15
	fi
	echo "Esperando ${WAIT} segundos..."
	sleep ${WAIT}
	echo "Iniciando OMXPlayer..."
	if [[ ${OMX_HDMI} -eq 1 ]]; then
		echo "Activando salida por HDMI..."
		start_omx="nice -10 omxplayer -r -o hdmi --live ${ENLACE_OMXPLAYER} > /dev/null 2>&1 &"
	else
		start_omx="nice -10 omxplayer -r --live ${ENLACE_OMXPLAYER} > /dev/null 2>&1 &"
	fi
	if [[ ${VERBOSE} -eq 1 ]]; then
		echo "Comando: ${start_omx}"
	fi
	${DIR}/start_omxplayer.sh "${start_omx}" > /dev/null 2>&1 &
fi

exit 0
