/*
 * Copyright 2011, Google Inc.
 * All rights reserved.
 *
 * Redistribution and use in source and binary forms, with or without
 * modification, are permitted provided that the following conditions are
 * met:
 *
 *     * Redistributions of source code must retain the above copyright
 * notice, this list of conditions and the following disclaimer.
 *     * Redistributions in binary form must reproduce the above
 * copyright notice, this list of conditions and the following disclaimer
 * in the documentation and/or other materials provided with the
 * distribution.
 *     * Neither the name of Google Inc. nor the names of its
 * contributors may be used to endorse or promote products derived from
 * this software without specific prior written permission.
 *
 * THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
 * "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
 * LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
 * A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
 * OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
 * SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
 * LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
 * DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
 * THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 * (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 * OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 */

#ifndef NIXYSA_STATIC_GLUE_PPAPI_COMMON_H_
#define NIXYSA_STATIC_GLUE_PPAPI_COMMON_H_

#include <string>

#include "ppapi/cpp/instance.h"

// Creates an empty JavaScript array.
pp::Var CreateArray(pp::Instance* instance);

namespace glue {
namespace globals {

// This function must be implemented by the user of the glue generator.
// It need not do anything, but it's where errors in the glue will be reported.
// Currently the glue code only reports user errors such as parameter type
// mismatches.
void SetLastError(pp::Instance* instance, const char* error);

#ifdef PROFILE_GLUE

#define GLUE_SCOPED_PROFILE(instance, key, name) \
  glue::globals::ScopedProfile name((instance), (key))
#define GLUE_SCOPED_PROFILE_STOP(name) name.Stop()
#define GLUE_PROFILE_START(instance, key) \
  glue::globals::ProfileStart((instance), (key))
#define GLUE_PROFILE_STOP(instance, key) \
  glue::globals::ProfileStop((instance), (key))
#define GLUE_PROFILE_RESET(instance) glue::globals::ProfileReset(instance)
#define GLUE_PROFILE_TO_STRING(instance) \
  glue::globals::ProfileToString(instance)

// These functions must be implemented by the user of the glue generator if
// profiling is desired.
void ProfileStart(pp::Instance* instance, const std::string& key);
void ProfileStop(pp::Instance* instance, const std::string& key);
void ProfileReset(pp::Instance* instance);
std::string ProfileToString(pp::Instance* instance);

class ScopedProfile {
 public:
  ScopedProfile(pp::Instance* instance, const std::string& key) :
      instance_(instance), key_(key), stopped_(false) {
    GLUE_PROFILE_START(instance_, key_);
  }
  ~ScopedProfile() {
    if (!stopped_) {
      GLUE_PROFILE_STOP(instance_, key_);
    }
  }
  void Stop() {
    GLUE_PROFILE_STOP(instance_, key_);
    stopped_ = true;
  }
 private:
  std::string key_;
  pp::Instance* instance_;
  bool stopped_;

  // Disallow implicit contructors.
  ScopedProfile(const ScopedProfile&);
  void operator=(const ScopedProfile&);
};

#else  // PROFILE_GLUE

#define GLUE_SCOPED_PROFILE(instance, key, name)
#define GLUE_SCOPED_PROFILE_STOP(name)
#define GLUE_PROFILE_START(instance, key)
#define GLUE_PROFILE_STOP(instance, key)
#define GLUE_PROFILE_RESET(instance)
#define GLUE_PROFILE_TO_STRING(instance) ""

#endif  // PROFILE_GLUE

}  // namespace globals
}  // namespace glue

#endif  // NIXYSA_STATIC_GLUE_PPAPI_COMMON_H_
