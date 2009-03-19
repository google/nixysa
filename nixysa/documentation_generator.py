#!/usr/bin/python2.4
#
# Copyright 2008 Google Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Documentation generator.

This module implements the generator for documentation code.
"""

import cpp_utils
import syntax_tree


class DocumentationItem(object):
  """Documentation member information storage class.

  This class stores all the information contained within a documentation block.

  Attributes:
    name: the name of the member which this block documents.
    type: the definition type of the member which this block documents.
    id: the id of the member which this block documents.
    text: the documentation text
    member_found: true if corresponding member was found during parsing

  TODO: Add parameter documentation verification
  """

  def __init__(self, verbatim_block):
    """Inits a DocumentationItem.

    Args:
      verbatim_block: the verbatim documentation to initialize documentation
                      item
    """
    if 'name' in verbatim_block.attributes:
      self.name = verbatim_block.attributes['name']
    else:
      self.name = ''
    if 'type' in verbatim_block.attributes:
      self.type_defn = verbatim_block.attributes['type']
    else:
      self.type_defn = ''
    if 'id' in verbatim_block.attributes:
      self.id = verbatim_block.attributes['id']
    else:
      self.id = ''
    self.text = verbatim_block.text
    self.member_found = False
    self.VerifyDocumentationItem()

  def VerifyDocumentationItem(self):
    """Verifies that documentation block has the necessary information.

    TODO: Ultimately all items should have ids and this should just check for id
          validity.
    """
    if not self.type_defn and not self.id:
      print 'Documentation block %s has neither type nor id' % self.name
    # Check that text actually contains information
    cleaned_text = self.text
    cleaned_text.strip()
    if not cleaned_text:
      print 'Documentation block %s has no documentation text' % self.name
      

class DocumentationGenerator(object):
  """Documentation generator class.

  This class creates a file with the stubs for documentation based on the
  definitions in a syntax tree. The stubs will be filled with a simple
  place-holder description and it is up to the user to replace it with
  something more useful. Stubs will not be generated for members which
  already have a documentation block.

  This class is strongly based off of the HeaderGenerator class and follows
  the same structure of having functions named after each of the
  Definition classes in the syntax_tree.

  There are several todos for this class which will become necessary/usesful
  if the code tree becomes larger:
  - output documentation back into the idl file
  - generate unique ids for each member and associated documentation block
    so that we can eventually put all documentation either in a separate file
    or at the end of the file rather than embedded
  """

  def __init__(self, output_dir):
    self._output_dir = output_dir

  def TraverseDefinitionList(self, parent_section, scope, defn_list,
                             verbatim_dict, exclude_list):
    """Generates the documentation for all the definitions in a list.

    Args:
      parent_section: the main section of the parent scope.
      scope: the parent scope.
      defn_list: the list of definitions.
      verbatim_dict: dictionary of documentation blocks.
      exclude_list: the list of definitions to ignore.
    """
    for obj in syntax_tree.GetObjectsRecursive(defn_list):
      if not obj.defn_type in exclude_list:
        found_documentation = False
        if obj.name in verbatim_dict:
          doc_item_list = verbatim_dict[obj.name]
          for doc_item in doc_item_list:
            if doc_item.type_defn == obj.defn_type:
              if (not 'id' in obj.attributes or
                  doc_item.id == obj.attributes['id']):
                found_documentation = True
                doc_item.member_found = True
        if not found_documentation and obj.name is not None:
          # There is no current item.
          # Output error and add stub block to file.
          print 'No documentation found for %s %s' % (obj.defn_type, obj.name)
          print 'Generating documentation for %s %s' % (obj.defn_type, obj.name)
          doc_string = '[verbatim=docs,name=%s,type=%s' % (obj.name,
                                                           obj.defn_type)
          if 'id' in obj.attributes:
            doc_string += ',id=' + obj.attributes['id']
          filler_string = '%s %s' % (obj.defn_type, obj.name)
          doc_string += '] %{\n\t' + filler_string + '\n%}'
          parent_section.EmitCode(doc_string)

  def Generate(self, idl_file, namespace, defn_list, verbatim_dict):
    """Generate the file writer for the documentation.

    Args:
      idl_file: the source IDL file containing the definitions, as a
        idl_parser.File instance.
      namespace: a Definition for the global namespace.
      defn_list: the list of top-level definitions.
      verbatim_dict: the list of documentation blocks.

    Returns:
      A file writer.
    """
    writer = cpp_utils.CppFileWriter('%s/%s' % (self._output_dir,
                                                idl_file.documentation), False)
    main_section = writer.CreateSection('documentation')
    exclude_list = ['Namespace']
    self.TraverseDefinitionList(main_section, namespace, defn_list,
                                verbatim_dict, exclude_list)
                                
    return writer

  def FindTypeDefinitions(self, type_string, item_to_make, defn_list,
                          type_list):
    """Searches the definition list for items of a particular type.

    The type list will create a storage item of the type 'item_to_make'. Each
    entry in the dictionary is a list of all items with the same name.

    Args:
      type_string: name of the type match against.
      item_to_make: object to make if match is found.
      defn_list: the definition list to search through.
      type_list: current list of items of the same type.
    """
    for obj in syntax_tree.GetObjectsRecursive(defn_list):
      if obj.defn_type == type_string:
        try:
          object_name = obj.attributes['name']
          if not object_name in type_list:
            type_list[object_name] = []
          doc_item = item_to_make(obj)
          type_list[object_name].append(doc_item)
        except KeyError:
          print 'Object of type %s found with no name' % type_string

  def BuildExistingDocumentationDict(self, defn_list):
    """Builds a dictionary which maps members to their documentation.

    Args:
      defn_list: a syntax tree definition list

    Returns:
      a dictionary of members mapped to documentation
    """
    verbatim_dict = {}
    self.FindTypeDefinitions('Verbatim', DocumentationItem, defn_list,
                             verbatim_dict)
    return verbatim_dict

  def PrintDocumentationDict(self, verbatim_dict):
    """Prints the dictionary of documentation blocks.

    This is currently used for debugging.

    Args:
      verbatim_dict: the dictionary of documentation blocks.
    """
    print verbatim_dict
    for (i, j) in verbatim_dict.iteritems():
      print '%s has length %d' % (i, len(j))
      for k in j:
        print '   %s with type %s' % (k.name, k.type_defn)

  def CheckForDanglingDocumentation(self, documentation_list):
    """Checks to make sure all documentation blocks have a match.
    
    When the original list is parsed, each documentation block is marked when
    its corresponding member is found. At the end of parsing, we want to be sure
    all documentation had a matching member or else it should not be there.

    Args:
      documentation_list: dictionary of marked documentation blocks
    """
    for (object_name, object_list) in documentation_list.iteritems():
      for item in object_list:
        if not item.member_found:
          print 'Dangling Documentation for:'
          print '  %s %s, id = %s in %s' % (item.type_defn, item.name, item.id,
                                            object_name)
          print '  body: %s' % item.text


def ProcessFiles(output_dir, pairs, namespace):
  """Generates documentation stubs for all members.
    
  Args:
    output_dir: the output directory.
    pairs: a list of (idl_parser.File, syntax_tree.Definition list) describing
      the list of top-level definitions in each source file.
    namespace: a syntax_tree.Namespace for the global namespace.

  Returns:
    a list of cpp_utils.CppFileWriter, one for each output doc file.
  """
  generator = DocumentationGenerator(output_dir)
  writer_list = []
  for (f, defn) in pairs:
    verbatim_dict = generator.BuildExistingDocumentationDict(defn)
    writer = generator.Generate(f, namespace, defn, verbatim_dict)
    generator.CheckForDanglingDocumentation(verbatim_dict)
    # Only create file if there is something to create
    # There will be no file needed if all documentation is in order
    if not writer.GetSection('documentation').IsEmpty():
      writer_list.append(generator.Generate(f, namespace, defn, verbatim_dict))
  return writer_list


def main():
  pass
  
if __name__ == '__main__':
  main()
