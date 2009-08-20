#include <npapi.h>

extern "C" {
  const char *NP_GetMIMEDescription(void) {
    return "application/HelloWorld::Hello World Test";
  }

  NPError NP_GetValue(NPP instance, NPPVariable variable, void *value) {
    switch (variable) {
      case NPPVpluginNameString:
        *static_cast<const char **>(value) = "Hello World";
        break;
      case NPPVpluginDescriptionString:
        *static_cast<const char **>(value) = "Hello World Plugin";
        break;
      default:
        return NPERR_INVALID_PARAM;
        break;
    }
    return NPERR_NO_ERROR;
  }
}
