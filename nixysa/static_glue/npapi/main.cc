// Copyright 2008 Google Inc.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//      http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

#include <stdio.h>
#include <npupp.h>
#include <string>
#include "globals_glue.h"

extern "C" {
  NPError WINAPI NP_Initialize(NPNetscapeFuncs *browserFuncs);
  NPError WINAPI NP_GetEntryPoints(NPPluginFuncs *pluginFuncs);
  void WINAPI NP_Shutdown(void);

  NPError WINAPI NP_Initialize(NPNetscapeFuncs *browserFuncs) {
    return InitializeNPNApi(browserFuncs);
  }

  NPError WINAPI NP_GetEntryPoints(NPPluginFuncs *pluginFuncs) {
    pluginFuncs->version = 11;
    pluginFuncs->size = sizeof(pluginFuncs);
    pluginFuncs->newp = NPP_New;
    pluginFuncs->destroy = NPP_Destroy;
    pluginFuncs->setwindow = NPP_SetWindow;
    pluginFuncs->newstream = NPP_NewStream;
    pluginFuncs->destroystream = NPP_DestroyStream;
    pluginFuncs->asfile = NPP_StreamAsFile;
    pluginFuncs->writeready = NPP_WriteReady;
    pluginFuncs->write = (NPP_WriteProcPtr)NPP_Write;
    pluginFuncs->print = NPP_Print;
    pluginFuncs->event = NPP_HandleEvent;
    pluginFuncs->urlnotify = NPP_URLNotify;
    pluginFuncs->getvalue = NPP_GetValue;
    pluginFuncs->setvalue = NPP_SetValue;

    return NPERR_NO_ERROR;
  }

  void WINAPI NP_Shutdown(void) {
  }

  NPError NPP_New(NPMIMEType pluginType, NPP instance, uint16 mode, int16 argc,
                  char *argn[], char *argv[], NPSavedData *saved) {
    glue::InitializeGlue(instance);
    instance->pdata = glue::CreateStaticNPObject(instance, NULL);
    return NPERR_NO_ERROR;
  }

  NPError NPP_Destroy(NPP instance, NPSavedData **save) {
    NPObject *obj = static_cast<NPObject*>(instance->pdata);
    if (obj) {
      NPN_ReleaseObject(obj);
      instance->pdata = NULL;
    }

    return NPERR_NO_ERROR;
  }

  NPError NPP_SetWindow(NPP instance, NPWindow *window) {
    return NPERR_NO_ERROR;
  }

  NPError NPP_NewStream(NPP instance, NPMIMEType type, NPStream *stream,
                        NPBool seekable, uint16 *stype) {
    return NPERR_NO_ERROR;
  }

  NPError NPP_DestroyStream(NPP instance, NPStream *stream, NPReason reason) {
    return NPERR_NO_ERROR;
  }

  int32 NPP_WriteReady(NPP instance, NPStream *stream) {
    return 4096;
  }

  int32 NPP_Write(NPP instance, NPStream *stream, int32 offset, int32 len,
                  void *buffer) {
    return len;
  }

  void NPP_StreamAsFile(NPP instance, NPStream *stream, const char *fname) {
  }

  void NPP_Print(NPP instance, NPPrint *platformPrint) {
  }

  int16 NPP_HandleEvent(NPP instance, void *event) {
    return 0;
  }

  void NPP_URLNotify(NPP instance, const char *url, NPReason reason,
                     void *notifyData) {
  }

  NPError NPP_GetValue(NPP instance, NPPVariable variable, void *value) {
    if (variable == NPPVpluginScriptableNPObject) {
      void **v = static_cast<void **>(value);
      NPObject *obj = static_cast<NPObject *>(instance->pdata);

      // Return value is expected to be retained
      GLUE_PROFILE_START(instance, "retainobject");
      NPN_RetainObject(obj);
      GLUE_PROFILE_STOP(instance, "retainobject");
      *v = obj;
      return NPERR_NO_ERROR;
    }
    return NPERR_GENERIC_ERROR;
  }

  NPError NPP_SetValue(NPP instance, NPNVariable variable, void *value) {
    return NPERR_GENERIC_ERROR;
  }
}  // extern "C"
