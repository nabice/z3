############################################
# Copyright (c) 2012 Microsoft Corporation
# 
# Auxiliary scripts for generating Makefiles 
# and Visual Studio project files.
#
# Author: Leonardo de Moura (leonardo)
############################################
import os
import glob
import sets
from dependencies import *
from mk_exception import *

BUILD_DIR='build'
REV_BUILD_DIR='..'
SRC_DIR='src'
IS_WINDOW=False
CXX='g++'
MAKE='make'
if os.name == 'nt':
    IS_WINDOW=True
    CXX='cl'
    MAKE='nmake'
SHOW_CPPS = True

LIB_KIND = 0
EXE_KIND = 1

# Given a path dir1/subdir2/subdir3 returns ../../..
def reverse_path(p):
    l = p.split('/')
    n = len(l)
    r = '..'
    for i in range(1, n):
        r = '%s/%s' % (r, '..')
    return r

def mk_dir(d):
    if not os.path.exists(d):
        os.makedirs(d)

def set_build_dir(d):
    global BUILD_DIR
    BUILD_DIR = d
    REV_BUILD_DIR = reverse_path(d)

_UNIQ_ID = 0

def mk_fresh_name(prefix):
    global _UNIQ_ID
    r = '%s_%s' % (prefix, _UNIQ_ID)
    _UNIQ_ID = _UNIQ_ID + 1
    return r

_Id = 0
_Components = []
_ComponentNames = sets.Set()
_Name2Component = {}
_Processed_Headers = sets.Set()

def get_cpp_files(path):
    return filter(lambda f: f.endswith('.cpp'), os.listdir(path))

def find_all_deps(name, deps):
    new_deps = []
    for dep in deps:
        if dep in _ComponentNames:
            if not (dep in new_deps):
                new_deps.append(dep)
            for dep_dep in _Name2Component[dep].deps:
                if not (dep_dep in new_deps):
                    new_deps.append(dep_dep)
        else:
            raise MKException("Unknown component '%s' at '%s'." % (dep, name))
    return new_deps

class Component:
    def __init__(self, name, kind, path, deps):
        global BUILD_DIR, SRC_DIR, REV_BUILD_DIR
        if name in _ComponentNames:
            raise MKException("Component '%s' was already defined." % name)
        if path == None:
            path = name
        self.kind = kind
        self.name = name
        self.path = path
        self.deps = find_all_deps(name, deps)
        self.build_dir = path
        self.src_dir   = '%s/%s' % (SRC_DIR, path)
        self.to_src_dir = '%s/%s' % (REV_BUILD_DIR, self.src_dir)

    # Find fname in the include paths for the given component.
    # ownerfile is only used for creating error messages.
    # That is, we were looking for fname when processing ownerfile
    def find_file(self, fname, ownerfile):
        global _Name2Component
        full_fname = '%s/%s' % (self.src_dir, fname)
        if os.path.exists(full_fname):
            return self
        for dep in self.deps:
            c_dep = _Name2Component[dep]
            full_fname = '%s/%s' % (c_dep.src_dir, fname)
            if os.path.exists(full_fname):
                return c_dep
        raise MKException("Failed to find include file '%s' for '%s' when processing '%s'." % (fname, ownerfile, self.name))

    # Display all dependencies of file basename located in the given component directory.
    # The result is displayed at out
    def add_cpp_h_deps(self, out, basename):
        includes = extract_c_includes('%s/%s' % (self.src_dir, basename))
        out.write('%s/%s' % (self.to_src_dir, basename))
        for include in includes:
            owner = self.find_file(include, basename)
            out.write(' %s/%s.node' % (owner.build_dir, include))

    # Add a rule for each #include directive in the file basename located at the current component.
    def add_rule_for_each_include(self, out, basename):
        fullname = '%s/%s' % (self.src_dir, basename)
        includes = extract_c_includes(fullname)
        for include in includes:
            owner = self.find_file(include, fullname)
            owner.add_h_rule(out, include)

    # Display a Makefile rule for an include file located in the given component directory.
    # 'include' is something of the form: ast.h, polynomial.h
    # The rule displayed at out is of the form
    #     ast/ast_pp.h.node : ../src/util/ast_pp.h util/util.h.node ast/ast.h.node
    #       @echo "done" > ast/ast_pp.h.node
    def add_h_rule(self, out, include):
        include_src_path   = '%s/%s' % (self.to_src_dir, include)
        if include_src_path in _Processed_Headers:
            return
        _Processed_Headers.add(include_src_path)
        self.add_rule_for_each_include(out, include)
        include_node = '%s/%s.node' % (self.build_dir, include)
        out.write('%s: ' % include_node)
        self.add_cpp_h_deps(out, include)              
        out.write('\n')
        out.write('\t@echo done > %s\n' % include_node)

    def add_cpp_rules(self, out, include_defs, cppfile):
        self.add_rule_for_each_include(out, cppfile)
        objfile = '%s/%s$(OBJ_EXT)' % (self.build_dir, os.path.splitext(cppfile)[0])
        srcfile = '%s/%s' % (self.to_src_dir, cppfile)
        out.write('%s: ' % objfile)
        self.add_cpp_h_deps(out, cppfile)
        out.write('\n')
        if SHOW_CPPS:
            out.write('\t@echo %s\n' % cppfile)
        out.write('\t@$(CXX) $(CXXFLAGS) $(%s) $(CXX_OUT_FLAG)%s %s\n' % (include_defs, objfile, srcfile))

    def mk_makefile(self, out):
        include_defs = mk_fresh_name('includes')
        out.write('%s =' % include_defs)
        for dep in self.deps:
            out.write(' -I%s' % _Name2Component[dep].to_src_dir)
        out.write('\n')
        mk_dir('%s/%s' % (BUILD_DIR, self.build_dir))
        for cppfile in get_cpp_files(self.src_dir):
            self.add_cpp_rules(out, include_defs, cppfile)

class LibComponent(Component):
    def __init__(self, name, path, deps):
        Component.__init__(self, name, LIB_KIND, path, deps)

    def mk_makefile(self, out):
        Component.mk_makefile(self, out)
        # generate rule for lib
        objs = []
        for cppfile in get_cpp_files(self.src_dir):
            objfile = '%s/%s$(OBJ_EXT)' % (self.build_dir, os.path.splitext(cppfile)[0])
            objs.append(objfile)

        libfile = '%s/%s$(LIB_EXT)' % (self.build_dir, self.name)
        out.write('%s:' % libfile)
        for obj in objs:
            out.write(' ')
            out.write(obj)
        out.write('\n')
        out.write('\t@$(AR) $(AR_FLAGS) $(AR_OUTFLAG)%s' % libfile)
        for obj in objs:
            out.write(' ')
            out.write(obj)
        out.write('\n')
        out.write('%s: %s\n\n' % (self.name, libfile))

# Auxiliary function for sort_components
def comp_components(c1, c2):
    id1 = _Name2Component[c1].id
    id2 = _Name2Component[c2].id
    return id2 - id1

# Sort components based on (reverse) definition time
def sort_components(cnames):
    return sorted(cnames, cmp=comp_components)

class ExeComponent(Component):
    def __init__(self, name, exe_name, path, deps):
        Component.__init__(self, name, EXE_KIND, path, deps)
        if exe_name == None:
            exe_name = name
        self.exe_name = exe_name

    def mk_makefile(self, out):
        global _Name2Component
        Component.mk_makefile(self, out)
        # generate rule for exe

        exefile = '%s$(EXE_EXT)' % self.exe_name
        out.write('%s:' % exefile)
        deps = sort_components(self.deps)
        objs = []
        for cppfile in get_cpp_files(self.src_dir):
            objfile = '%s/%s$(OBJ_EXT)' % (self.build_dir, os.path.splitext(cppfile)[0])
            objs.append(objfile)
        for obj in objs:
            out.write(' ')
            out.write(obj)
        for dep in deps:
            c_dep = _Name2Component[dep]
            out.write(' %s/%s$(LIB_EXT)' % (c_dep.build_dir, c_dep.name))
        out.write('\n')
        out.write('\t$(LINK) $(LINK_OUT_FLAG)%s $(LINK_FLAGS)' % exefile)
        for obj in objs:
            out.write(' ')
            out.write(obj)
        for dep in deps:
            c_dep = _Name2Component[dep]
            out.write(' %s/%s$(LIB_EXT)' % (c_dep.build_dir, c_dep.name))
        out.write('\n')
        out.write('%s: %s\n\n' % (self.name, exefile))
            

def reg_component(name, c):
    global _Id, _Components, _ComponentNames, _Name2Component
    c.id = _Id
    _Id = _Id + 1
    _Components.append(c)
    _ComponentNames.add(name)
    _Name2Component[name] = c

def add_lib(name, deps=[], path=None):
    c = LibComponent(name, path, deps)
    reg_component(name, c)

def add_exe(name, deps=[], path=None, exe_name=None):
    c = ExeComponent(name, exe_name, path, deps)
    reg_component(name, c)

def mk_makefile():
    mk_dir(BUILD_DIR)
    out = open('%s/Makefile' % BUILD_DIR, 'w')
    out.write('# Automatically generated file. Generator: scripts/mk_make.py\n')
    out.write('include config.mk\n')
    for c in _Components:
        c.mk_makefile(out)

# add_lib('util')
# add_lib('polynomial', ['util'])
# add_lib('ast', ['util', 'polynomial'])
# mk_makefile()
