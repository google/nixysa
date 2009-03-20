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

#include <assert.h>
#include <string.h>

#ifdef OS_WINDOWS
#include <windows.h>
#define snprintf _snprintf
#endif

#ifdef OS_MACOSX
#include <Carbon/Carbon.h>
#endif

#ifdef OS_LINUX
#include <stdio.h>
#endif

#include <npapi.h>
#include <npruntime.h>
#include <string>
#include "common.h"
#include "npn_api.h"

//------------------------------------------------------------------------------
// UTF8ToString16
//------------------------------------------------------------------------------
bool UTF8ToString16(const char *in, int len, std::wstring *out16) {
  assert(in);
  assert(len >= 0);
  assert(out16);

  if (len == 0) {
    *out16 = L"";
    return true;
  }

#ifdef OS_MACOSX
  CFStringRef cfStr = CFStringCreateWithCString(kCFAllocatorDefault, in,
                                                kCFStringEncodingUTF8);
  if (!cfStr)
    return false;
  CFDataRef cfData = CFStringCreateExternalRepresentation(kCFAllocatorDefault,
                                              cfStr, kCFStringEncodingUTF32, 0);
  CFRelease(cfStr);
  if (!cfData)
    return false;
  int out_byte_len = CFDataGetLength(cfData);
  out_byte_len -= sizeof(wchar_t); // don't count the 32 bit BOM char at start
  int out_len = out_byte_len / sizeof(wchar_t);
  wchar_t *tmp = new wchar_t[out_len + 1];
  // start after the BOM, hence sizeof(wchar_t)
  CFDataGetBytes(cfData, CFRangeMake(sizeof(wchar_t), out_byte_len),
                 (UInt8*)tmp);
  CFRelease(cfData);
  tmp[out_len] = 0;
  out16->assign(tmp);
  delete[] tmp;
#endif

#ifdef OS_WINDOWS
  int out_len = MultiByteToWideChar(CP_UTF8, 0, in, len, NULL, 0);
  if (out_len <= 0)
    return false;
  wchar_t *tmp = new wchar_t[out_len + 1];
  out_len = MultiByteToWideChar(CP_UTF8, 0, in, len, tmp, out_len);
  if (out_len <= 0) {
    delete[] tmp;
    return false;
  }
  tmp[out_len] = 0;
  out16->assign(tmp);
  delete[] tmp;
#endif

#ifdef OS_LINUX
  // TODO: this is incorrect. Fix it.
  std::string string_in(in, len);
  *out16 = std::wstring(string_in.begin(), string_in.end());
#endif
  return true;
}

//------------------------------------------------------------------------------
// String16ToUTF8
//------------------------------------------------------------------------------
bool String16ToUTF8(const wchar_t *in, int len, std::string *out8) {
  assert(in);
  assert(len >= 0);
  assert(out8);

  if (len == 0) {
    *out8 = "";
    return true;
  }

#ifdef OS_MACOSX
  CFDataRef cfWCharData = CFDataCreate(kCFAllocatorDefault, (const UInt8*)in,
                                       len * sizeof(wchar_t));
  CFStringRef cfStr = CFStringCreateFromExternalRepresentation(
                                              kCFAllocatorDefault, cfWCharData,
                                              kCFStringEncodingUTF32);
  CFRelease(cfWCharData);
  CFDataRef cfUTF8Data = CFStringCreateExternalRepresentation(
                                               kCFAllocatorDefault,
                                               cfStr, kCFStringEncodingUTF8, 0);
  CFRelease(cfStr);
  int out_len = CFDataGetLength(cfUTF8Data);
  char *tmp = new char[out_len + 1];
  CFDataGetBytes(cfUTF8Data, CFRangeMake(0, out_len), (UInt8*)tmp);
  tmp[out_len] = '\0';
  CFRelease(cfUTF8Data);
  if (out_len <= 0) {
    delete[] tmp;
    return false;
  }
  tmp[out_len] = 0;
  out8->assign(tmp);
  delete[] tmp;
#endif

#ifdef OS_WINDOWS
  int out_len = WideCharToMultiByte(CP_UTF8, 0, in, len, NULL, 0, NULL, NULL);
  if (out_len <= 0)
    return false;
  char *tmp = new char[out_len + 1];
  out_len = WideCharToMultiByte(CP_UTF8, 0, in, len, tmp, out_len,
                                NULL, NULL);
  if (out_len <= 0) {
    delete[] tmp;
    return false;
  }
  tmp[out_len] = 0;
  out8->assign(tmp);
  delete[] tmp;
#endif

#ifdef OS_LINUX
  // TODO: this is incorrect. Fix it.
  std::wstring string_in(in, len);
  *out8 = std::string(string_in.begin(), string_in.end());
#endif
  return true;
}

bool String16ToNPVariant(const std::wstring &in, NPVariant *variant) {
  std::string out8;
  bool r = String16ToUTF8(in.c_str(), in.size(), &out8);
  if (!r) {
    VOID_TO_NPVARIANT(*variant);
    return false;
  }
  return StringToNPVariant(out8, variant);
}

bool StringToNPVariant(const std::string &in, NPVariant *variant) {
  size_t length = in.size();
  NPUTF8 *chars = static_cast<NPUTF8 *>(NPN_MemAlloc(length));
  if (!chars) {
    VOID_TO_NPVARIANT(*variant);
    return false;
  }
  memcpy(chars, in.c_str(), length);
  STRINGN_TO_NPVARIANT(chars, length, *variant);
  return true;
}

std::string UIntToString(unsigned int value) {
  // Biggest unsigned int is 2^32-1 or about 4*10^9 so we need at most 10
  // digits plus the terminal NUL.
  char buffer[11] = {0};
  int result = snprintf(buffer, 11, "%u", value);
  return std::string(buffer);
}

bool GetNPObjectProperty(NPP npp, NPObject *object, const char *name,
                         NPVariant *output) {
  GLUE_PROFILE_START(npp, "NPN_GetStringIdentifier");
  NPIdentifier identifier = NPN_GetStringIdentifier(name);
  GLUE_PROFILE_STOP(npp, "NPN_GetStringIdentifier");
  GLUE_PROFILE_START(npp, "NPN_HasProperty");
  bool result = NPN_HasProperty(npp, object, identifier);
  GLUE_PROFILE_STOP(npp, "NPN_HasProperty");
  if (!result) return false;
  GLUE_PROFILE_START(npp, "NPN_GetProperty");
  result = NPN_GetProperty(npp, object, identifier, output);
  GLUE_PROFILE_STOP(npp, "NPN_GetProperty");
  return result;
}

bool GetNPArrayProperty(NPP npp, NPObject *object, int index,
                        NPVariant *output) {
  GLUE_PROFILE_START(npp, "NPN_GetIntIdentifier");
  NPIdentifier identifier = NPN_GetIntIdentifier(index);
  GLUE_PROFILE_STOP(npp, "NPN_GetIntIdentifier");
  // Safari doesn't implement NPN_HasProperty, the work-around is too slow for
  // big arrays, so don't check for the existence of int properties - the user
  // may get unexpected error messages, but what can we do.
  if (!IsHasPropertyWorkaround()) {
    GLUE_PROFILE_START(npp, "NPN_HasProperty");
    bool result = NPN_HasProperty(npp, object, identifier);
    GLUE_PROFILE_STOP(npp, "NPN_HasProperty");
    if (!result) return false;
  }
  GLUE_PROFILE_START(npp, "NPN_GetProperty");
  bool result = NPN_GetProperty(npp, object, identifier, output);
  GLUE_PROFILE_STOP(npp, "NPN_GetProperty");
  return result;
}

NPObject *CreateArray(NPP npp) {
  // Evaluate '[]' in JavaScript, which will create a new array.
  // We need to retrieve the 'global context' too execute into, that's what
  // global_object is.
  NPObject *global_object;
  GLUE_PROFILE_START(npp, "CreateArray");
  GLUE_PROFILE_START(npp, "getvalue");
  NPN_GetValue(npp, NPNVWindowNPObject, &global_object);
  GLUE_PROFILE_STOP(npp, "getvalue");
  NPString string;
  string.utf8characters = "[]";
  string.utf8length = strlen(string.utf8characters);
  NPVariant result;
  GLUE_PROFILE_START(npp, "evaluate");
  bool temp = NPN_Evaluate(npp, global_object, &string, &result);
  GLUE_PROFILE_STOP(npp, "evaluate");
  if (!temp) return NULL;
  if (NPVARIANT_IS_OBJECT(result)) {
    return NPVARIANT_TO_OBJECT(result);
  } else {
    GLUE_PROFILE_START(npp, "NPN_ReleaseVariantValue");
    NPN_ReleaseVariantValue(&result);
    GLUE_PROFILE_STOP(npp, "NPN_ReleaseVariantValue");
    return NULL;
  }
  GLUE_PROFILE_STOP(npp, "CreateArray");
}

ScopedId::ScopedId(NPIdentifier name) {
  text_ = NPN_UTF8FromIdentifier(name);
}

ScopedId::~ScopedId() {
  NPN_MemFree(text_);
}
