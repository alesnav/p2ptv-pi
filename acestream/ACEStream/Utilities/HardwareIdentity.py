#Embedded file name: ACEStream\Utilities\HardwareIdentity.pyo
import sys
if sys.platform == 'win32':
    try:
        import wmi
    except:
        pass

    def get_hardware_key():
        dmi_wmi = wmi.WMI()
        memory = 0
        for i in dmi_wmi.Win32_PhysicalMemory():
            memory += int(i.Capacity)

        hdd = ''
        model_hdd = 0
        serial_hdd = 0
        for partition in dmi_wmi.Win32_DiskDriveToDiskPartition():
            boot = partition.Dependent.BootPartition
            if boot:
                if not model_hdd:
                    try:
                        model_hdd = partition.Antecedent.Model
                    except:
                        pass

                if not serial_hdd:
                    try:
                        serial_hdd = partition.Antecedent.SerialNumber
                    except:
                        pass

            else:
                if not model_hdd:
                    try:
                        model_hdd = partition.Antecedent.Model
                    except:
                        pass

                if not serial_hdd:
                    try:
                        serial_hdd = partition.Antecedent.SerialNumber
                    except:
                        pass

        if not model_hdd or not serial_hdd:
            for media in dmi_wmi.Win32_PhysicalMedia():
                if not model_hdd:
                    try:
                        model_hdd = media.Model
                    except:
                        pass

                if not serial_hdd:
                    try:
                        serial_hdd = media.SerialNumber
                    except:
                        pass

        hdd = '%s-%s' % (model_hdd, serial_hdd)
        hdd = hdd.replace(' ', '_')
        id = '%s::%s' % (hdd, memory)
        return id


else:
    import os

    def get_hardware_key():
        memory = 0
        memory_cmd = "grep MemTotal /proc/meminfo | awk '{print $2}'"
        pipe = os.popen(memory_cmd, 'r')
        if pipe:
            memory = int(pipe.read())
            pipe.close()
        memory *= 1024
        hdd = ''
        hdd_cmd = "ls -l /dev/disk/by-id/ | grep -w 'sd%s\\|hd%s' | awk '{print $8}'"
        alphabet = 'abcdefghijklmnopqrstuvwxyz'
        hdds = ''
        for character in alphabet:
            pipe = os.popen(hdd_cmd % (character, character), 'r')
            if pipe:
                hdds = pipe.read()
                pipe.close()
            if hdds != '':
                break

        if hdds != '':
            hdd_arr = hdds.split('\n')
            for item in hdd_arr:
                if item[:3] == 'ata':
                    hdd = item[4:]
                    break
                elif item[:4] == 'scsi':
                    hdd = item[10:]
                    break

        id = '%s::%s' % (hdd, memory)
        return id
