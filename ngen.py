#!/usr/bin/python
import os
import re
import sys
import subprocess
import time
import shlex

# Notes:
# arch support is currently only for macros, not commands
#

import android
import win32
import linux
import osx

import argparse

class Config:
	def __init__(C, name):
		C.extension = ""
		C.name = name
		C.cpps = set()
		C.mms = set()
		C.cs = set()
		C.asms = set()
		C.objs = set()
		C.metals = set()
		C.objraw = set()
		C.target = ""
		C.targets = set()
		C.paramz = {}



class NGen:
	def __init__(N):
		N.modules = {}
		N.configs = {}
		N.platforms = ["win32", "linux", "osx", "android"]
		N.archs = {}
		N.active_alias = []
		N.alias = {}

		N.modules["win32"] = win32
		N.modules["linux"] = linux
		N.modules["osx"] = osx
		N.modules["android"] = android

		N.tempdir = os.path.abspath("_temp")
		N.outdir = os.path.abspath("_out")
		N.default_config = ""
		N.g_include_prefix="-I"
		N.obj_extension = ".o"
		N.configs["__default"] = Config("__default")

		pathname = os.path.dirname(sys.argv[0])        
		N.code_path = os.path.abspath(pathname)

		N.parser = argparse.ArgumentParser()
		N.parser.add_argument('-v', '--verbose', help='verbose, do lots of logging', action="store_true")
		N.parser.add_argument('-c', '--clean', help='clean before running', action="store_true")
		N.parser.add_argument('-t', help='target platform', choices=N.platforms)
		for mod_name in N.modules:
			N.modules[mod_name].RegisterActions(N)

		N.args = N.parser.parse_args()
		N.verbose = N.args.verbose;
		if N.verbose:
			print("VERBOSE!!\n")
		if N.args.clean:
			os.system("ninja -t clean")

		N.active_platform = sys.platform

		if N.active_platform == "darwin":
			N.active_platform = "osx"

		if N.active_platform == "linux2":
			N.active_platform = "linux"

		N.host_platform = N.active_platform
		
		if N.args.t:
			N.active_platform = N.args.t
		N.active_module = N.modules[N.active_platform]


		if N.active_platform == "win32":
			N.obj_extension = ".obj"

		if N.active_platform == "win32":
			N.g_include_prefix = "/I"

		N.paths_processed = set()

		N.active_module.Init(N)
		for arch in N.archs:
			N.archs[arch] = Config(arch)



	def GetConfig(N, s):
		if s == "":
			s = "__default";
		return N.configs[s];

	def MergeConfigs(N):
		default = N.configs["__default"]
		for cfg_name in N.configs:
			if cfg_name != "__default":
				cfg = N.configs[cfg_name]
				cfg.cpps = cfg.cpps | default.cpps
				cfg.mms = cfg.mms | default.mms
				cfg.cs = cfg.cs | default.cs
				cfg.asms = cfg.asms | default.asms
				cfg.objs = cfg.objs | default.objs
				cfg.metals = cfg.metals | default.metals
				cfg.objraw = cfg.objraw | default.objraw
				cfg.target = default.target

	def GetExtension(N):
		if hasattr(N.active_module, 'Extension'):
			return N.active_module.Extension(N)
		else:
			return ""

	def GetTargetName(N, cfg, arch):
		ext = N.GetExtension()
		arch_ext = N.GetArchSuffix(arch)
		return "$outdir/%s_%s%s%s" % (cfg.target, cfg.name, arch_ext, ext)

	def SplitPath(N, p):
		idx_ext = p.rfind('.')
		idx_path = max(p.rfind('\\'), p.rfind('/'))
		extension_less = p
		extension = ""
		if idx_ext > idx_path:
			extension_less = p[:idx_ext];
			extension = p[idx_ext+1:];
		idx_platform = extension_less.rfind('_')
		platform = ""
		if idx_platform > idx_path:
			platform = extension_less[idx_platform+1:]
		return extension, platform;

	def SplitCommand(N, c):
		idx_platform = c.rfind('.');
		platform = ""
		command = c
		if idx_platform > 0:
			platform = c[idx_platform+1:]
			command = c[:idx_platform];
		#print("Split Command '%s' :: c '%s' plat '%s'" % (c, command, platform))
		return command, platform;

	def SplitCommand3(N, c):
		platform = ""
		config = ""
		arch = ""
		c1 = ""
		command, c0 = N.SplitCommand(c)
		if c0 != "":
			command, c1 = N.SplitCommand(command)
			if c0 in N.platforms:
				platform = c0
			elif c0 in N.configs:
				config = c0
			elif c0 in N.archs:
				arch = c0
			else:
				print("unknown suffix %s" % c0)
				exit(1)
		if c1 in N.platforms:
			platform = c1
		elif c1 in N.configs:
			config = c1
		elif c1 in N.archs:
			arch = c1
		elif c1 != "":
			print("unknown suffix %s" % c1)
			exit(1)
	
		return command, platform, config, arch

	def PlatformMatch(N, p):
		return (not p in N.platforms) or p == "" or p == N.active_platform or p in N.active_alias
	
	def ArchMatch(N, arch):
		return arch != "" and arch in N.archs

	def ProcessFile1(N, p):
		N.ProcessFile(p, N.GetConfig(""))

	def ProcessFile(N, p, cfg):
		print("p " + p);
		if os.path.isfile(p):
			extension, platform = N.SplitPath(p)
			if N.PlatformMatch(platform):
				if extension == "c":
					cfg.cs.add(p)
					print("C " + p)
				if extension == "cpp":
					cfg.cpps.add(p)
					print("CPP " + p)
				if extension == "mm":
					cfg.mms.add(p)
					print("MM " + p)
				if extension == "metal":
					cfg.metals.add(p)
					print("METAL " + p)
				if extension == "s" or extension == "S":
					cfg.asms.add(p)
					print("ASM " + p)
		else:
			print("missing file %s\n" % p)

	def ProcessPath(N, d, cfg):
		abspth = os.path.abspath(d)
		extension, platform = N.SplitPath(abspth)
		if N.PlatformMatch(platform):
			if not abspth in N.paths_processed:
				N.paths_processed.add(abspth)
				if os.path.isdir(abspth):
					for filename in os.listdir(abspth):
						p = os.path.join(d, filename)
						N.ProcessFile(p, cfg)
				else:
					print("invalid path %s" % abspth)

	def GetObjName(N, name, ext, cfg, arch):
		rawbase = os.path.basename(name)[:-len(ext)]
		raw = rawbase
		idx = 0
		while raw in cfg.objraw:
			raw = "%s_%d" %(rawbase, idx)
			idx = idx + 1
		cfg.objraw.add(raw)
		archstr = arch
		if(archstr):
			archstr = "/" + archstr
		objname = "$tempdir/" + N.active_platform + "/" + cfg.name + archstr + "/" + raw
		return objname, name

	def AddToEnv(N, Name, Value):
		Current = os.environ[Name]
		New = Current + "" + Value
		os.environ[Name] = New

	def EnvironmentReplace(N, str):
		regex = r"(.*)(\%[\w]+\%)(.*)"
		m = re.match(regex, str)
		while m and m.lastindex == 3:
			s1 = m.group(1)
			s2 = m.group(2)
			s3 = m.group(3)
			s2lower = s2[1:len(s2)-1];
			s2x = s2lower.upper()
			if hasattr(N, s2lower):
				value = getattr(N, s2lower)
				str = s1 + value + s3
			elif s2x in os.environ:
				str = s1 + os.environ[s2x]+ s3
			else:
				str = s1 + s3
			m = re.match(regex, str)
		return str

	def ParamMakePathsAbsolute(N, Param, Value):
		if Param == "includepath" or Param == "libpath":
			Array = Value.split(" ")
			Value = "";
			for arg in Array:
				if os.path.exists(arg):
					Value += N.g_include_prefix + "\"%s\" " % os.path.abspath(arg);
					print( "INCLUDE '%s'" % Value)
				else:
					print("Failing to find path %s" % (arg))
					exit(1)
		return Value.strip()


	def AddParamInternal(N, cfg, Param, V):
		value = cfg.paramz.get(Param, "");
		V = N.EnvironmentReplace(V)
		V = N.ParamMakePathsAbsolute(Param, V)
		value = value.strip() + " " + V;
		cfg.paramz[Param] = value;

	def AddArchParam(N, Param, V, arch):
		arch = N.archs[arch]
		N.AddParamInternal(arch, Param, V)

	def AddParam(N, Param, V, config = ""):
		cfg = N.GetConfig(config)
		N.AddParamInternal(cfg, Param, V)

	def AddRule(N, f, str):
		for cfg_name in N.configs:
			if cfg_name != "__default":
				f.write(str.replace("%%", cfg_name))

	def Run(N):
		N.NgenProcessFile("ngen.cfg")
		for mod_name in N.modules:
			if N.modules[mod_name].ExecuteActions(N):
				print('custom action done')
				exit(0)
		N.WriteBuildFile()

	def PlatformAlias(N, alias, src):
		print("adding alias %s" % alias)
		N.platforms.append(alias)
		N.alias[alias] = src
		if N.active_platform in src:
			print("adding active alias: %s" % alias)
			N.active_alias.append(alias)
		else:
			print("not adding alias %s :: %s" %(alias, N.active_platform))

	def NgenProcessFile(N, filename):
		f = open(filename)
		line_idx = 0;

		for line in f:
			line_idx = line_idx + 1
			line = line.strip()
			if len(line) > 0 and line[0] != '#':
				IsCommand = line[0] == '.'
				if IsCommand:
					line = line[1:].strip()
				r = re.search(r'([ \t])', line)
				if r:
					idx = r.end()
				else:
					idx = len(line)

				command = line[:idx].strip()
				arg = line[idx:].strip()
				if N.verbose:
					print( "%s:%d : %s  CC %s" %(filename, line_idx, line, command))
				command, platform, config, arch = N.SplitCommand3(command);
				cfg = N.GetConfig(config)
				print(" COMMAND ('%s' '%s' '%s' '%s') --> %s" % (command, platform, config, arch, arg))
				if IsCommand:
					if command == "break":
						print("BREAK!\n")
						exit(1)
					elif command == "ngen":
						if N.PlatformMatch(platform):
							print("recursive ngen %s !!!\n" %(arg))
							if os.path.isfile(arg):
								N.NgenProcessFile(arg)
							else:
								print("file was not found!\n")
					elif command == "tempdir":
						N.tempdir = os.path.abspath(arg)
						print("tempdir is now " + N.tempdir);
					elif command == "outdir":
						N.outdir = os.path.abspath(arg)
					elif command == "config":
						N.configs[arg] = Config(arg)
						if N.default_config == "":
							N.default_config = arg
							print("default config is now " + N.default_config)
					elif(command == "dir"):
						if N.PlatformMatch(platform):
							N.ProcessPath(arg, cfg)
					elif(command == "file"):
						if N.PlatformMatch(platform):
							N.ProcessFile(arg, cfg)
					elif(command == "target"):
						cfg.target = arg.strip()
						N.target = cfg.target
						print("CFG TARGET IS " + cfg.target);
						cfg.targets.add(cfg.target)
					elif command == "platform-alias":
						argsplit = arg.split()
						N.PlatformAlias(argsplit[0],argsplit[1:])
					elif N.active_module.HandleCommand(N, command, arg, cfg):
						pass # custom command
					else:
						print("unknown command " + command + " ARG " + arg)
						exit(1)
				else:
					l0 = command
					l1 = arg
					if arch != "":
						if N.ArchMatch(arch):
							N.AddArchParam(l0, l1, arch)
							N.AddParam(l0, "")
					elif N.PlatformMatch(platform):
						if arch != "":
							print("fail!")
							exit(1)
						N.AddParam(l0, l1, config);
						if config != "":
							N.AddParam(l0, "")



	def GetArchSuffix(N, arch):
		if arch != "":
			return "_%s" % arch				
		else:
			return ""


	def WriteBuildFile(N):
		N.active_module.PreMerge(N)		
		N.MergeConfigs()

		if N.default_config == "":
			print("default config missing. please specify a config with .config")
			exit(1)
		
		with open("build.ninja", "w") as f:
			f.write("\n# Generated by ngen.py\n\n")
			f.write("outdir = " + os.path.join(N.outdir, N.active_platform) + "\n\n")
			f.write("tempdir = " + N.tempdir + "\n\n")
			if hasattr(N.active_module, 'WriteAssignments'):
				N.active_module.WriteAssignments(N, f)
			else:
				f.write("c = clang\n\n")
				f.write("cxx = clang++\n\n")

			default_cfg = N.configs["__default"]
			for key in default_cfg.paramz.keys():
				value = default_cfg.paramz.get(key, "")
				f.write( "%s = %s\n" % (key.strip(), value.strip()))
			f.write("\n\n")

			for arch in N.archs:
				suff = "_%s" % arch
				arch_cfg = N.archs[arch]
				for key in default_cfg.paramz.keys():
					value = arch_cfg.paramz.get(key, "")
					f.write( "%s%s = $%s %s\n" % (key.strip(), suff, key.strip(), value.strip()))
				f.write("\n\n")
			
			f.write("\n\n")

			archs = N.archs
			if len(archs) == 0:
				archs = {"":""}
			for arch in archs:
				arch_suffix = N.GetArchSuffix(arch)
				for cfg_name in N.configs:
					suffix = "";
					cfg = N.configs[cfg_name]
					for key in N.configs["__default"].paramz.keys():
						value = cfg.paramz.get(key, "")
						if cfg_name != "__default":
							f.write( "%s_%s%s = $%s%s %s\n" % (key.strip(), cfg_name, arch_suffix, key.strip(), arch_suffix, value.strip()))
					f.write("\n")
			f.write("\n\n")

			rule_filename = N.code_path + "/rules." + N.active_platform
			print("loading rules from " + rule_filename)
			rule_lines = []
			with open(rule_filename, "r") as rules:
				for rule_line in rules:
					rule_lines.append(rule_line)
			for arch in archs:
				arch_suffix = N.GetArchSuffix(arch)
				for cfg_name in N.configs:
					if cfg_name != "__default":
						repl = "%s%s" %(cfg_name, arch_suffix)
						for rule_line in rule_lines:
							f.write(rule_line.replace("%%", repl))
			f.write("""


rule ngen
  command = %s %s/ngen.py -t %s

""" % (sys.executable, N.code_path, N.active_platform))
			for arch in archs:
				arch_suffix = N.GetArchSuffix(arch)
				
				f.write("#rules for %s\n" % arch_suffix)
				for cfg_name in N.configs:
					if cfg_name != "__default":
						objs = set()
						cfg = N.configs[cfg_name]
						suff = "%s%s" % (cfg_name, arch_suffix)
						obj_extension = N.obj_extension

						for v in cfg.cs:
							objname, fullname = N.GetObjName(v, ".c", cfg, arch)
							objs.add(objname+obj_extension)
							f.write("build %s: c_%s %s\n" % (objname+obj_extension, suff, fullname))

						for v in cfg.cpps:
							objname, fullname = N.GetObjName(v, ".cpp", cfg, arch)
							objs.add(objname+obj_extension)
							f.write("build %s: cxx_%s %s\n" % (objname+obj_extension, suff, fullname))

						for v in cfg.mms:
							objname, fullname = N.GetObjName(v, ".mm", cfg, arch)
							objs.add(objname+obj_extension)
							f.write("build %s: mxx_%s %s\n" % (objname+obj_extension, suff, fullname))

						for v in cfg.asms:
							objname, fullname = N.GetObjName(v, ".s", cfg, arch)
							objs.add(objname+obj_extension)
							f.write("build %s: asm_%s %s\n" % (objname+obj_extension, suff, fullname))

						for v in cfg.metals:
							objname, fullname = N.GetObjName(v, ".metal", cfg, arch)
							f.write("build %s: metal_%s %s\n" % (objname+".air", suff, fullname))
							f.write("build %s: metallib_%s %s\n" % (objname+".metallib", suff, objname+".air"))
							cfg.targets.add(objname+".metallib")
						ext = N.GetExtension()

						f.write("build %s: link_%s" % (N.GetTargetName(cfg, arch), suff))
						for obj in objs:
							f.write(" " + obj)
						f.write("\n\n")

						#archs[arch].objs[cfg_name] = objs

			f.write("build build.ninja: ngen ngen.cfg\n\n");
			f.write("default build.ninja ")
			cfg_default = N.configs[N.default_config]
			for arch in archs:
				f.write("%s " % N.GetTargetName(cfg_default, arch))
			f.write("\n\n")
			for cfg_name in N.configs:
				if cfg_name != "__default":
					cfg = N.configs[cfg_name];
					f.write("build %s: phony " % cfg_name)
					for arch in archs:
						f.write("%s " % N.GetTargetName(cfg, arch))
					f.write("\n\n")


			f.write("build all: phony ");
			for cfg_name in N.configs:
				if cfg_name != "__default":
					cfg = N.configs[cfg_name];
					for arch in archs:
						f.write("%s " % N.GetTargetName(cfg, arch))
			f.write("\n\n")
			if hasattr(N.active_module, 'WriteCustomRules'):
				N.active_module.WriteCustomRules(N, f)



N = NGen()
N.Run()


