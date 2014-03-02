#Embedded file name: ACEStream\Core\Video\MediaInfo.pyo
import os
from ctypes import *
from ACEStream.Core.Utilities.logger import log, log_exc
if os.name == 'nt' or os.name == 'dos' or os.name == 'os2' or os.name == 'ce':
    MediaInfoDLL_Handler = windll.MediaInfo
    MustUseAnsi = 0
else:
    MediaInfoDLL_Handler = CDLL('libmediainfo.so.0')
    MustUseAnsi = 1
MEDIAINFO_STREAM_GENERAL = 0
MEDIAINFO_STREAM_VIDEO = 1
MEDIAINFO_STREAM_AUDIO = 2
MEDIAINFO_STREAM_TEXT = 3
MEDIAINFO_STREAM_CHAPTERS = 4
MEDIAINFO_STREAM_IMAGE = 5
MEDIAINFO_STREAM_MENU = 6
MEDIAINFO_STREAM_MAX = 7

class Info:
    Name, Text, Measure, Options, Name_Text, Measure_Text, Info, HowTo, Max = range(9)


class InfoOption:
    ShowInInform, Reserved, ShowInSupported, TypeOfValue, Max = range(5)


class FileOptions:
    Nothing, Recursive, CloseAll, xxNonexx_3, Max = range(5)


class MediaInfo:
    MediaInfo_New = MediaInfoDLL_Handler.MediaInfo_New
    MediaInfo_New.argtypes = []
    MediaInfo_New.restype = c_void_p
    MediaInfo_New_Quick = MediaInfoDLL_Handler.MediaInfo_New_Quick
    MediaInfo_New_Quick.argtypes = [c_wchar_p, c_wchar_p]
    MediaInfo_New_Quick.restype = c_void_p
    MediaInfoA_New_Quick = MediaInfoDLL_Handler.MediaInfoA_New_Quick
    MediaInfoA_New_Quick.argtypes = [c_char_p, c_char_p]
    MediaInfoA_New_Quick.restype = c_void_p
    MediaInfo_Delete = MediaInfoDLL_Handler.MediaInfo_Delete
    MediaInfo_Delete.argtypes = [c_void_p]
    MediaInfo_Delete.restype = None
    MediaInfo_Open = MediaInfoDLL_Handler.MediaInfo_Open
    MediaInfo_Open.argtype = [c_void_p, c_wchar_p]
    MediaInfo_Open.restype = c_size_t
    MediaInfoA_Open = MediaInfoDLL_Handler.MediaInfoA_Open
    MediaInfoA_Open.argtype = [c_void_p, c_char_p]
    MediaInfoA_Open.restype = c_size_t
    MediaInfo_Open_Buffer = MediaInfoDLL_Handler.MediaInfo_Open_Buffer
    MediaInfo_Open_Buffer.argtype = [c_void_p,
     c_void_p,
     c_size_t,
     c_void_p,
     c_size_t]
    MediaInfo_Open_Buffer.restype = c_size_t
    MediaInfo_Open_Buffer_Init = MediaInfoDLL_Handler.MediaInfo_Open_Buffer_Init
    MediaInfo_Open_Buffer_Init.argtype = [c_void_p, c_uint64, c_uint64]
    MediaInfo_Open_Buffer_Init.restype = c_size_t
    MediaInfo_Open_Buffer_Continue = MediaInfoDLL_Handler.MediaInfo_Open_Buffer_Continue
    MediaInfo_Open_Buffer_Continue.argtype = [c_void_p, c_void_p, c_size_t]
    MediaInfo_Open_Buffer_Continue.restype = c_size_t
    MediaInfo_Open_Buffer_Continue_GoTo_Get = MediaInfoDLL_Handler.MediaInfo_Open_Buffer_Continue_GoTo_Get
    MediaInfo_Open_Buffer_Continue_GoTo_Get.argtype = [c_void_p]
    MediaInfo_Open_Buffer_Continue_GoTo_Get.restype = c_uint64
    MediaInfo_Open_Buffer_Finalize = MediaInfoDLL_Handler.MediaInfo_Open_Buffer_Finalize
    MediaInfo_Open_Buffer_Finalize.argtype = [c_void_p]
    MediaInfo_Open_Buffer_Finalize.restype = c_size_t
    MediaInfo_Save = MediaInfoDLL_Handler.MediaInfo_Save
    MediaInfo_Save.argtype = [c_void_p]
    MediaInfo_Save.restype = c_size_t
    MediaInfo_Close = MediaInfoDLL_Handler.MediaInfo_Close
    MediaInfo_Close.argtype = [c_void_p]
    MediaInfo_Close.restype = None
    MediaInfo_Inform = MediaInfoDLL_Handler.MediaInfo_Inform
    MediaInfo_Inform.argtype = [c_void_p, c_size_t]
    MediaInfo_Inform.restype = c_wchar_p
    MediaInfoA_Inform = MediaInfoDLL_Handler.MediaInfoA_Inform
    MediaInfoA_Inform.argtype = [c_void_p, c_size_t]
    MediaInfoA_Inform.restype = c_char_p
    MediaInfo_GetI = MediaInfoDLL_Handler.MediaInfo_GetI
    MediaInfo_GetI.argtype = [c_void_p,
     c_size_t,
     c_size_t,
     c_size_t,
     c_size_t]
    MediaInfo_GetI.restype = c_wchar_p
    MediaInfoA_GetI = MediaInfoDLL_Handler.MediaInfoA_GetI
    MediaInfoA_GetI.argtype = [c_void_p,
     c_size_t,
     c_size_t,
     c_size_t,
     c_size_t]
    MediaInfoA_GetI.restype = c_char_p
    MediaInfo_Get = MediaInfoDLL_Handler.MediaInfo_Get
    MediaInfo_Get.argtype = [c_void_p,
     c_size_t,
     c_size_t,
     c_wchar_p,
     c_size_t,
     c_size_t]
    MediaInfo_Get.restype = c_wchar_p
    MediaInfoA_Get = MediaInfoDLL_Handler.MediaInfoA_Get
    MediaInfoA_Get.argtype = [c_void_p,
     c_size_t,
     c_size_t,
     c_wchar_p,
     c_size_t,
     c_size_t]
    MediaInfoA_Get.restype = c_char_p
    MediaInfo_SetI = MediaInfoDLL_Handler.MediaInfo_SetI
    MediaInfo_SetI.argtype = [c_void_p,
     c_wchar_p,
     c_size_t,
     c_size_t,
     c_size_t,
     c_wchar_p]
    MediaInfo_SetI.restype = c_void_p
    MediaInfoA_SetI = MediaInfoDLL_Handler.MediaInfoA_SetI
    MediaInfoA_SetI.argtype = [c_void_p,
     c_char_p,
     c_size_t,
     c_size_t,
     c_size_t,
     c_wchar_p]
    MediaInfoA_SetI.restype = c_void_p
    MediaInfo_Set = MediaInfoDLL_Handler.MediaInfo_Set
    MediaInfo_Set.argtype = [c_void_p,
     c_wchar_p,
     c_size_t,
     c_size_t,
     c_wchar_p,
     c_wchar_p]
    MediaInfo_Set.restype = c_size_t
    MediaInfoA_Set = MediaInfoDLL_Handler.MediaInfoA_Set
    MediaInfoA_Set.argtype = [c_void_p,
     c_char_p,
     c_size_t,
     c_size_t,
     c_wchar_p,
     c_wchar_p]
    MediaInfoA_Set.restype = c_size_t
    MediaInfo_Option = MediaInfoDLL_Handler.MediaInfo_Option
    MediaInfo_Option.argtype = [c_void_p, c_wchar_p, c_wchar_p]
    MediaInfo_Option.restype = c_wchar_p
    MediaInfoA_Option = MediaInfoDLL_Handler.MediaInfoA_Option
    MediaInfoA_Option.argtype = [c_void_p, c_char_p, c_char_p]
    MediaInfoA_Option.restype = c_char_p
    MediaInfo_State_Get = MediaInfoDLL_Handler.MediaInfo_State_Get
    MediaInfo_State_Get.argtype = [c_void_p]
    MediaInfo_State_Get.restype = c_size_t
    MediaInfo_Count_Get = MediaInfoDLL_Handler.MediaInfo_Count_Get
    MediaInfo_Count_Get.argtype = [c_void_p, c_size_t, c_size_t]
    MediaInfo_Count_Get.restype = c_size_t
    Handle = c_void_p(0)
    MustUseAnsi = 0

    def __init__(self):
        self.Handle = self.MediaInfo_New()
        self.MediaInfoA_Option(self.Handle, 'CharSet', 'UTF-8')

    def __del__(self):
        self.MediaInfo_Delete(self.Handle)

    def Open(self, File):
        if type(File) == str:
            return self.MediaInfoA_Open(self.Handle, File)
        elif MustUseAnsi:
            return self.MediaInfoA_Open(self.Handle, File.encode('utf-8'))
        else:
            return self.MediaInfo_Open(self.Handle, File)

    def Open_Buffer(self, Begin, Begin_Size, End = None, End_Size = 0):
        return self.MediaInfo_Open_Buffer(self.Handle, Begin, Begin_Size, End, End_Size)

    def Open_Buffer_Init(self, file_size = -1, file_offset = 0):
        return self.MediaInfo_Open_Buffer_Init(self.Handle, c_uint64(file_size), c_uint64(file_offset))

    def Open_Buffer_Continue(self, buf, buf_size):
        return self.MediaInfo_Open_Buffer_Continue(self.Handle, buf, buf_size)

    def Open_Buffer_Continue_GoTo_Get(self):
        return self.MediaInfo_Open_Buffer_Continue_GoTo_Get(self.Handle)

    def Open_Buffer_Finalize(self):
        return self.MediaInfo_Open_Buffer_Finalize(self.Handle)

    def Save(self):
        return self.MediaInfo_Save(self.Handle)

    def Close(self):
        return self.MediaInfo_Close(self.Handle)

    def Inform(self):
        if MustUseAnsi:
            return unicode(self.MediaInfoA_Inform(self.Handle, 0), 'utf_8')
        else:
            return self.MediaInfo_Inform(self.Handle, 0)

    def Get(self, StreamKind, StreamNumber, Parameter, InfoKind = Info.Text, SearchKind = Info.Name):
        if type(Parameter) == str:
            return unicode(self.MediaInfoA_Get(self.Handle, StreamKind, StreamNumber, Parameter, InfoKind, SearchKind), 'utf_8')
        elif MustUseAnsi:
            return unicode(self.MediaInfoA_Get(self.Handle, StreamKind, StreamNumber, Parameter.encode('utf-8'), InfoKind, SearchKind), 'utf_8')
        else:
            return self.MediaInfo_Get(self.Handle, StreamKind, StreamNumber, Parameter, InfoKind, SearchKind)

    def GetI(self, StreamKind, StreamNumber, Parameter, InfoKind = Info.Text):
        if MustUseAnsi:
            return unicode(self.MediaInfoA_GetI(self.Handle, StreamKind, StreamNumber, Parameter, InfoKind), 'utf_8')
        else:
            return self.MediaInfo_GetI(self.Handle, StreamKind, StreamNumber, Parameter, InfoKind)

    def Set(self, ToSet, StreamKind, StreamNumber, Parameter, OldParameter = u''):
        if type(Parameter) == str and type(OldParameter) == unicode:
            Parameter = Parameter.decode('utf-8')
        if type(Parameter) == unicode and type(OldParameter) == str:
            OldParameter = OldParameter.decode('utf-8')
        if type(Parameter) == str:
            return self.MediaInfoA_Set(self.Handle, ToSet, StreamKind, StreamNumber, Parameter, OldParameter)
        elif MustUseAnsi:
            return self.MediaInfoA_Set(self.Handle, ToSet, StreamKind, StreamNumber, Parameter.encode('utf-8'), OldParameter.encode('utf-8'))
        else:
            return self.MediaInfo_Set(self.Handle, ToSet, StreamKind, StreamNumber, Parameter, OldParameter)

    def SetI(self, ToSet, StreamKind, StreamNumber, Parameter, OldValue):
        if MustUseAnsi:
            return self.MediaInfoA_SetI(self.Handle, ToSet, StreamKind, StreamNumber, Parameter, OldValue.encode('utf-8'))
        else:
            return self.MediaInfo_SetI(self.Handle, ToSet, StreamKind, StreamNumber, Parameter, OldValue)

    def Option(self, Option, Value = u''):
        if type(Option) == str and type(Value) == unicode:
            Option = Option.decode('utf-8')
        if type(Option) == unicode and type(Value) == str:
            Value = Value.decode('utf-8')
        if type(Option) == str:
            return unicode(self.MediaInfoA_Option(self.Handle, Option.encode('utf-8'), Value.encode('utf-8')), 'utf_8')
        elif MustUseAnsi:
            return unicode(self.MediaInfoA_Option(self.Handle, Option.encode('utf-8'), Value.encode('utf-8')), 'utf_8')
        else:
            return self.MediaInfo_Option(self.Handle, Option, Value)

    def Option_Static(self, Option, Value = u''):
        if type(Option) == str and type(Value) == unicode:
            Option = Option.decode('utf-8')
        if type(Option) == unicode and type(Value) == str:
            Value = Value.decode('utf-8')
        if type(Option) == str:
            return unicode(self.MediaInfoA_Option(None, Option, Value), 'utf_8')
        elif MustUseAnsi:
            return unicode(self.MediaInfoA_Option(None, Option.encode('utf-8'), Value.encode('utf-8')), 'utf_8')
        else:
            return self.MediaInfo_Option(None, Option, Value)

    def State_Get(self):
        return self.MediaInfo_State_Get(self.Handle)

    def Count_Get(self, StreamKind, StreamNumber = -1):
        return self.MediaInfo_Count_Get(self.Handle, StreamKind, StreamNumber)


class MediaInfoList:
    MediaInfoList_New = MediaInfoDLL_Handler.MediaInfoList_New
    MediaInfoList_New.argtype = []
    MediaInfoList_New.restype = c_void_p
    MediaInfoList_New_Quick = MediaInfoDLL_Handler.MediaInfoList_New_Quick
    MediaInfoList_New_Quick.argtype = [c_wchar_p, c_wchar_p]
    MediaInfoList_New_Quick.restype = c_void_p
    MediaInfoList_Delete = MediaInfoDLL_Handler.MediaInfoList_Delete
    MediaInfoList_Delete.argtype = [c_void_p]
    MediaInfoList_Open = MediaInfoDLL_Handler.MediaInfoList_Open
    MediaInfoList_Open.argtype = [c_void_p, c_wchar_p, c_void_p]
    MediaInfoList_Open.restype = c_void_p
    MediaInfoList_Open_Buffer = MediaInfoDLL_Handler.MediaInfoList_Open_Buffer
    MediaInfoList_Open_Buffer.argtype = [c_void_p,
     c_void_p,
     c_void_p,
     c_void_p,
     c_void_p]
    MediaInfoList_Open_Buffer.restype = c_void_p
    MediaInfoList_Save = MediaInfoDLL_Handler.MediaInfoList_Save
    MediaInfoList_Save.argtype = [c_void_p, c_void_p]
    MediaInfoList_Save.restype = c_void_p
    MediaInfoList_Close = MediaInfoDLL_Handler.MediaInfoList_Close
    MediaInfoList_Close.argtype = [c_void_p, c_void_p]
    MediaInfoList_Inform = MediaInfoDLL_Handler.MediaInfoList_Inform
    MediaInfoList_Inform.argtype = [c_void_p, c_void_p, c_void_p]
    MediaInfoList_Inform.restype = c_wchar_p
    MediaInfoList_GetI = MediaInfoDLL_Handler.MediaInfoList_GetI
    MediaInfoList_GetI.argtype = [c_void_p,
     c_void_p,
     c_void_p,
     c_void_p,
     c_void_p,
     c_void_p]
    MediaInfoList_GetI.restype = c_wchar_p
    MediaInfoList_Get = MediaInfoDLL_Handler.MediaInfoList_Get
    MediaInfoList_Get.argtype = [c_void_p,
     c_void_p,
     c_void_p,
     c_void_p,
     c_wchar_p,
     c_void_p,
     c_void_p]
    MediaInfoList_Get.restype = c_wchar_p
    MediaInfoList_SetI = MediaInfoDLL_Handler.MediaInfoList_SetI
    MediaInfoList_SetI.argtype = [c_void_p,
     c_wchar_p,
     c_void_p,
     c_void_p,
     c_void_p,
     c_void_p,
     c_wchar_p]
    MediaInfoList_SetI.restype = c_void_p
    MediaInfoList_Set = MediaInfoDLL_Handler.MediaInfoList_Set
    MediaInfoList_Set.argtype = [c_void_p,
     c_wchar_p,
     c_void_p,
     c_void_p,
     c_void_p,
     c_wchar_p,
     c_wchar_p]
    MediaInfoList_Set.restype = c_void_p
    MediaInfoList_Option = MediaInfoDLL_Handler.MediaInfoList_Option
    MediaInfoList_Option.argtype = [c_void_p, c_wchar_p, c_wchar_p]
    MediaInfoList_Option.restype = c_wchar_p
    MediaInfoList_State_Get = MediaInfoDLL_Handler.MediaInfoList_State_Get
    MediaInfoList_State_Get.argtype = [c_void_p]
    MediaInfoList_State_Get.restype = c_void_p
    MediaInfoList_Count_Get = MediaInfoDLL_Handler.MediaInfoList_Count_Get
    MediaInfoList_Count_Get.argtype = [c_void_p,
     c_void_p,
     c_void_p,
     c_void_p]
    MediaInfoList_Count_Get.restype = c_void_p
    MediaInfoList_Count_Get_Files = MediaInfoDLL_Handler.MediaInfoList_Count_Get_Files
    MediaInfoList_Count_Get_Files.argtype = [c_void_p]
    MediaInfoList_Count_Get_Files.restype = c_void_p
    Handle = c_void_p(0)

    def __init__(self):
        self.Handle = MediaInfoList_New()

    def __del__(self):
        MediaInfoList_Delete(self.Handle)

    def Open(self, Files, Options = FileOptions.Nothing):
        return MediaInfoList_Open(self.Handle, Files, Options)

    def Open_Buffer(self, Begin, Begin_Size, End = None, End_Size = 0):
        return MediaInfoList_Open_Buffer(self.Handle, Begin, Begin_Size, End, End_Size)

    def Save(self, FilePos):
        return MediaInfoList_Save(self.Handle, FilePos)

    def Close(self, FilePos):
        MediaInfoList_Close(self.Handle, FilePos)

    def Inform(self, FilePos, Reserved = 0):
        return MediaInfoList_Inform(self.Handle, FilePos, Reserved)

    def GetI(self, FilePos, StreamKind, StreamNumber, Parameter, InfoKind = Info.Text):
        return MediaInfoList_GetI(self.Handle, FilePos, StreamKind, StreamNumber, Parameter, InfoKind)

    def Get(self, FilePos, StreamKind, StreamNumber, Parameter, InfoKind = Info.Text, SearchKind = Info.Name):
        return MediaInfoList_Get(self.Handle, FilePos, StreamKind, StreamNumber, Parameter, InfoKind, SearchKind)

    def SetI(self, ToSet, FilePos, StreamKind, StreamNumber, Parameter, OldParameter = u''):
        return MediaInfoList_SetI(self, Handle, ToSet, FilePos, StreamKind, StreamNumber, Parameter, OldParameter)

    def Set(self, ToSet, FilePos, StreamKind, StreamNumber, Parameter, OldParameter = u''):
        return MediaInfoList_Set(self.Handle, ToSet, FilePos, StreamKind, StreamNumber, Parameter, OldParameter)

    def Option(self, Option, Value = u''):
        return MediaInfoList_Option(self.Handle, Option, Value)

    def Option_Static(self, Option, Value = u''):
        return MediaInfoList_Option(None, Option, Value)

    def State_Get(self):
        return MediaInfoList_State_Get(self.Handle)

    def Count_Get(self, FilePos, StreamKind, StreamNumber):
        return MediaInfoList_Count_Get(self.Handle, FilePos, StreamKind, StreamNumber=-1)

    def Count_Get_Files(self):
        return MediaInfoList_Count_Get_Files(self.Handle)
