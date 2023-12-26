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

DEFAULT_NAME = "___default_config"

def SuffixFixup(suffix):
	if suffix != "":
		return "_%s" % suffix
	return suffix


def MergeSuffix(suffix, parent_suffix):
	if parent_suffix != "":
		return "%s_%s" % (parent_suffix, suffix)
	else:
		return suffix

def PathFix(str): #..
	if str[0] == "\"" and str[-1] == "\"":
		print("PATH FIX %s" % str);
		return str[1:-1]
	return str


class Config:
	def __init__(C, name, parent, is_target, is_active):
		C.extension = ""
		C.name = name
		C.cpps = set()
		C.mms = set()
		C.cs = set()
		C.asms = set()
		C.objs = set()
		C.metals = set()
		C.objraw = set()
		C.paramz = {}
		if ~is_target:
			if parent == "":
				C.parent = DEFAULT_NAME
			else:
				C.parent = parent
		else:
			C.parent = ""

		C.is_target = is_target
		C.is_active = is_active
		C.target_configs = []
		C.level = 999 if is_target else -1
		C.suffix = ""

	def AddDefaultParams(C):
		C.paramz["cflags"] = "";
		C.paramz["includepath"] = "";
		C.paramz["ldflags"] = "";
		C.paramz["libpath"] = "";


class NGen:
	def __init__(N):
		N.modules = {}
		N.configs = {}
		N.configs_ordered = []
		N.all_targets = []
		N.platforms = ["win32", "linux", "osx", "android"]
		N.archs = {}
		N.active_alias = []
		N.alias = {}
		N.current_target = ""
		N.target_active = False
		N.default_target = "" 
		N.ngen_files = set()

		N.modules["win32"] = win32
		N.modules["linux"] = linux
		N.modules["osx"] = osx
		N.modules["android"] = android

		N.tempdir = os.path.abspath("_temp")
		N.outdir = os.path.abspath("_out")
		N.default_config = ""
		N.g_include_prefix="-I"
		N.obj_extension = ".o"
		N.configs[DEFAULT_NAME] = Config(DEFAULT_NAME, "", False, True)
		N.configs[DEFAULT_NAME].AddDefaultParams();

		N.pathname = os.path.dirname(sys.argv[0])        
		N.code_path = os.path.abspath(N.pathname)
		N.code_path_rel = os.path.relpath(N.pathname)

		N.parser = argparse.ArgumentParser()
		N.parser.add_argument('-v', '--verbose', help='verbose, do lots of logging', action="store_true")
		N.parser.add_argument('-c', '--clean', help='clean before running', action="store_true")
		N.parser.add_argument('-t', help='target platform', choices=N.platforms)
		for mod_name in N.modules:
			N.modules[mod_name].RegisterActions(N)

		N.args = N.parser.parse_args()
		N.verbose = N.args.verbose;
		N.parse_file = ""
		N.parse_line = 0
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
		if N.target_active:
			if s != "":
				print("Cant specify subconfig inside target %s" % s)
				exit(1)
			return N.configs[N.current_target]
		if s == "":
			s = DEFAULT_NAME;
		return N.configs[s];


	#copy all parent flags.
	def MergeConfigs(N):
		default = N.configs[DEFAULT_NAME]
		default.level = 0;
		remaining = 1
		while remaining != 0: # loop repeatedly, because the cfgs do not come in order
			remaining = 0
			for cfg_name in N.configs:
				cfg = N.configs[cfg_name]
				if cfg_name != DEFAULT_NAME and not cfg.is_target:
					parent_cfg = N.configs[cfg.parent]
					if parent_cfg.level >= 0:
						N.configs_ordered.append(cfg_name)
						#merge stuff in
						cfg.level = parent_cfg.level + 1
						cfg.cpps = cfg.cpps | default.cpps
						cfg.mms = cfg.mms | default.mms
						cfg.cs = cfg.cs | default.cs
						cfg.asms = cfg.asms | default.asms
						cfg.objs = cfg.objs | default.objs
						cfg.metals = cfg.metals | default.metals
						cfg.objraw = cfg.objraw | default.objraw
						cfg.suffix = cfg_name
						cfg.is_active == cfg.is_active and parent_cfg.is_active
					else:
						remaining += 1

		for target_name in N.all_targets:
			cfg = N.configs[target_name]
			if not cfg.target_configs:
				cfg.target_configs = N.configs_ordered
		print("hello")


	def GetExtension(N):
		if hasattr(N.active_module, 'Extension'):
			return N.active_module.Extension(N)
		else:
			return ""

	def GetTargetPath(N, target_name, cfg):
		ext = N.GetExtension()
		#arch_ext = N.GetArchSuffix(arch)
		return "$outdir/%s_%s%s" % (target_name, cfg.name, ext)

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
		return N.target_active or ((not p in N.platforms) or p == "" or p == N.active_platform or p in N.active_alias)
	
	def PlatformMatchMultiple(N, platforms):
		for plat in platforms:
			if plat == N.active_platform or plat in N.active_alias:
				return True
		return False


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
				if extension == "s" or extension == "S" or extension == "asm":
					cfg.asms.add(p)
					print("ASM " + p)
		else:
			print("*** MISSING FILE %s\n" % p)
			exit(1)

	def ProcessPath(N, d, cfg):
		abspth = os.path.abspath(d)
		extension, platform = N.SplitPath(abspth)
		if N.PlatformMatch(platform):
			if not abspth in N.paths_processed:
				N.paths_processed.add(abspth)
				if os.path.isdir(abspth):
					for filename in os.listdir(abspth):
						p = os.path.join(d, filename)
						if not os.path.isdir(p):
							N.ProcessFile(p, cfg)
				else:
					print("invalid path %s" % abspth)

	def GetObjName(N, name, ext, cfg):
		rawbase = os.path.basename(name)[:-len(ext)]
		raw = rawbase
		idx = 0
		while raw in cfg.objraw:
			raw = "%s_%d" %(rawbase, idx)
			idx = idx + 1
		cfg.objraw.add(raw)
		archstr = ""
		#arch
		#if(archstr):
		#	archstr = "/" + archstr
		objname = "$tempdir/" + N.active_platform + "/" + cfg.suffix + "/" + raw
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
				arg = PathFix(arg);
				print("HELLO %s" % arg);
				if os.path.exists(arg):
					Value += N.g_include_prefix + "\"%s\" " % os.path.abspath(arg);
					print( "INCLUDE '%s'" % Value)
				else:
					N.ParseError("Failing to find path %s" % str(arg))
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
			if cfg_name != DEFAULT_NAME:
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

	def ParseError(N, error_msg):
		print("%s:%d ParseError %s" % (N.parse_file, N.parse_line, error_msg));
		exit(1)


	def NgenProcessFile(N, filename):
		f = open(filename)
		line_idx = 0;
		N.ngen_files.add(filename)

		for line in f:
			line_idx = line_idx + 1
			N.parse_file = filename
			N.parse_line = line_idx
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
				args = arg.split();
				if N.verbose:
					print( "%s:%d : %s  CC %s" %(filename, line_idx, line, command))
				command, platform, config, arch = N.SplitCommand3(command);
				cfg = N.GetConfig(config)
				is_target = cfg.is_target
				print(" COMMAND ('%s' '%s' '%s' '%s') --> %s" % (command, platform, config, arch, arg))
				if IsCommand:
					if command == "break":
						N.ParseError("BREAK");
					elif command == "ngen":
						assert not is_target
						if N.PlatformMatch(platform):
							print("recursive ngen %s !!!\n" %(arg))
							if os.path.isfile(arg):
								N.NgenProcessFile(arg)
							else:
								print("file was not found!\n")
					elif command == "tempdir":
						assert not is_target
						N.tempdir = os.path.abspath(arg)
						print("tempdir is now " + N.tempdir);
					elif command == "outdir":
						assert not is_target
						N.outdir = os.path.abspath(arg)
					elif command == "config":
						assert not is_target
						parent = ""
						num_args = len(args)
						if(num_args>1):
							parent = args[1];
						platform_match = True
						if num_args > 2:
							platform_match = N.PlatformMatchMultiple(args[2:])

						N.configs[args[0]] = Config(args[0], parent, False, platform_match)
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
						assert not is_target

						target_name = arg.strip()
						if hasattr(N.configs, target_name):
							print("already has attr " + target_name)
						N.configs[target_name] = Config(target_name, "", True, True)
						N.current_target = target_name
						N.target_active = True
						N.all_targets.append(target_name)
						if N.default_target == "":
							N.default_target = target_name
					elif command == "end":
						assert N.target_active
						N.current_target = ""
						N.target_active = False

					elif command == "platform-alias":
						assert not is_target
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
#						if config != "":
#							N.AddParam(l0, "")



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


			default_cfg = N.configs[DEFAULT_NAME]
			f.write("# CFG: DEFAULT\n");
			for key in default_cfg.paramz.keys():
				value = default_cfg.paramz.get(key, "")
				f.write( "%s = %s\n" % (key.strip(), value.strip()))

			f.write("\n\n")

			for cfg_name in N.configs_ordered:
				cfg = N.configs[cfg_name]
				if cfg.is_active:
					f.write("# CFG: %s\n" % cfg_name)
					parent_cfg = N.configs[cfg.parent]
					suffix = SuffixFixup(cfg.suffix)
					parent_suffix = SuffixFixup(parent_cfg.suffix)
					for key in cfg.paramz.keys() | parent_cfg.paramz.keys():
						value = ""
						if key in cfg.paramz.keys():
							value = cfg.paramz.get(key)
						else:
							cfg.paramz[key] = ""
						k = key.strip()
						f.write("%s%s = $%s%s %s\n" % (k, suffix, k, parent_suffix, value.strip()))

					f.write("\n\n")

			for target_name in N.all_targets:
				cfg = N.configs[target_name]
				for parent_cfg in cfg.target_configs:
					parent_cfg = N.configs[parent_cfg]
					if parent_cfg.is_active:
						parent_suffix = SuffixFixup(parent_cfg.suffix)
						suffix = SuffixFixup("%s_%s" %(parent_cfg.suffix, target_name))
						f.write("# CFG: %s_%s\n" % (parent_cfg.suffix, target_name))
						for key in cfg.paramz.keys() | parent_cfg.paramz.keys():
							value = ""
							if key in cfg.paramz.keys():
								value = cfg.paramz.get(key)
							else:
								cfg.paramz[key] = ""
							k = key.strip()
							f.write("%s%s = $%s%s %s\n" % (k, suffix, k, parent_suffix, value.strip()))
						f.write("\n\n")


			f.write("\n\n")

			# for arch in N.archs: 
			# 	suff = "_%s" % arch
			# 	arch_cfg = N.archs[arch]
			# 	for key in default_cfg.paramz.keys():
			# 		value = arch_cfg.paramz.get(key, "")
			# 		f.write( "%s%s = $%s %s\n" % (key.strip(), suff, key.strip(), value.strip()))
			# 	f.write("\n\n")
			
			# f.write("\n\n")

			# archs = N.archs
			# if len(archs) == 0:
			# 	archs = {"":""}
			# for arch in archs:
			# 	arch_suffix = N.GetArchSuffix(arch)
			# 	for cfg_name in N.configs:
			# 		suffix = "";
			# 		cfg = N.configs[cfg_name]
			# 		for key in N.configs[DEFAULT_NAME].paramz.keys():
			# 			value = cfg.paramz.get(key, "")
			# 			if cfg_name != DEFAULT_NAME:
			# 				f.write( "%s_%s%s = $%s%s %s\n" % (key.strip(), cfg_name, arch_suffix, key.strip(), arch_suffix, value.strip()))
			# 		f.write("\n")
			# f.write("\n\n")

			rule_filename = N.code_path + "/rules." + N.active_platform
			N.ngen_files.add(N.code_path_rel + "/rules." + N.active_platform)
			print("loading rules from " + rule_filename)
			rule_lines = []
			with open(rule_filename, "r") as rules:
				for rule_line in rules:
					rule_lines.append(rule_line)

			for cfg_name in N.configs_ordered:
				if cfg_name != DEFAULT_NAME:
					repl = "%s" %(cfg_name)
					f.write("# CFG %s rules\n\n" % repl)
					for rule_line in rule_lines:
						f.write(rule_line.replace("%%", repl))
					f.write("\n\n")

			for target_name in N.all_targets:
				cfg = N.configs[target_name]
				for parent_cfg in cfg.target_configs:
					parent_cfg = N.configs[parent_cfg]
					if parent_cfg.is_active:
						parent_suffix = parent_cfg.suffix
						suffix = "%s_%s" %(parent_suffix, target_name)
						f.write("# TARGET CFG %s rules\n\n" % suffix)
						for rule_line in rule_lines:
							f.write(rule_line.replace("%%", suffix))
						f.write("\n\n")


			f.write("""


rule ngen
  command = %s %s/ngen.py -t %s

""" % (sys.executable, N.code_path, N.active_platform))
			for cfg_name in N.configs_ordered:
				objs = set()
				cfg = N.configs[cfg_name]
				if cfg.is_active:
					f.write("# CFG %s\n\n" % cfg_name)
					suff = cfg_name
					obj_extension = N.obj_extension

					for v in cfg.cs:
						objname, fullname = N.GetObjName(v, ".c", cfg)
						objs.add(objname+obj_extension)
						f.write("build %s: c_%s %s\n" % (objname+obj_extension, suff, fullname))

					for v in cfg.cpps:
						objname, fullname = N.GetObjName(v, ".cpp", cfg)
						objs.add(objname+obj_extension)
						f.write("build %s: cxx_%s %s\n" % (objname+obj_extension, suff, fullname))

					for v in cfg.mms:
						objname, fullname = N.GetObjName(v, ".mm", cfg)
						objs.add(objname+obj_extension)
						f.write("build %s: mxx_%s %s\n" % (objname+obj_extension, suff, fullname))

					for v in cfg.asms:
						objname, fullname = N.GetObjName(v, ".s", cfg)
						objs.add(objname+obj_extension)
						f.write("build %s: asm_%s %s\n" % (objname+obj_extension, suff, fullname))
					cfg.objs = objs
					f.write("\n\n")

			for target_name in N.all_targets:
				cfg = N.configs[target_name]

				for parent_cfg in cfg.target_configs:
					objs = set()
					parent_cfg = N.configs[parent_cfg]
					if parent_cfg.is_active:
						parent_suffix = parent_cfg.suffix
						#target_suffix = SuffixFixup(parent_suffix)
						suffix = "%s_%s" %(parent_suffix, target_name)
						f.write("# TARGET CFG %s\n\n" % suffix)
						suff = suffix
						obj_extension = N.obj_extension

						for v in cfg.cs:
							objname, fullname = N.GetObjName(v, ".c", parent_cfg)
							objs.add(objname+obj_extension)
							f.write("build %s: c_%s %s\n" % (objname+obj_extension, suff, fullname))

						for v in cfg.cpps:
							objname, fullname = N.GetObjName(v, ".cpp", parent_cfg)
							objs.add(objname+obj_extension)
							f.write("build %s: cxx_%s %s\n" % (objname+obj_extension, suff, fullname))

						for v in cfg.mms:
							objname, fullname = N.GetObjName(v, ".mm", parent_cfg)
							objs.add(objname+obj_extension)
							f.write("build %s: mxx_%s %s\n" % (objname+obj_extension, suff, fullname))

						for v in cfg.asms:
							objname, fullname = N.GetObjName(v, ".s", parent_cfg)
							objs.add(objname+obj_extension)
							f.write("build %s: asm_%s %s\n" % (objname+obj_extension, suff, fullname))


						target_path = N.GetTargetPath(target_name, parent_cfg)
						ext = N.GetExtension()
						f.write("build %s: link_%s" % (target_path, suffix))
						for obj in objs:
							f.write(" " + obj)
						for obj in parent_cfg.objs:
							f.write(" " + obj)
						f.write("\n\n")


			f.write("build build.ninja: ngen ");
			for ngen_file in N.ngen_files:
				f.write("%s " % ngen_file)
			f.write("\n\n");


			cfg_default = N.configs[N.default_config]


			f.write("# one target all config aliases\n");

			for target_name in N.all_targets:
				cfg = N.configs[target_name]
				f.write("build %s: phony " % target_name)
				for parent_cfg in cfg.target_configs:
					parent_cfg = N.configs[parent_cfg]
					if parent_cfg.is_active:
						f.write("%s " % (N.GetTargetPath(target_name, parent_cfg) ) )
				f.write("\n")
			f.write("\n")

			f.write("# one target one config aliases\n");
			for target_name in N.all_targets:
				cfg = N.configs[target_name]
				for parent_cfg in cfg.target_configs:
					parent_cfg = N.configs[parent_cfg]
					if parent_cfg.is_active:
						f.write("build %s_%s: phony %s\n" % (target_name, parent_cfg.name, N.GetTargetPath(target_name, parent_cfg) ) )
			f.write("\n")


			f.write("# one config all target aliases\n");
			for cfg_name in N.configs_ordered:
				cfg = N.configs[cfg_name]
				if cfg.is_active:
					target_names = set()
					for target_name in N.all_targets:
						target_cfg = N.configs[target_name]
						if cfg_name in target_cfg.target_configs:
							target_names.add(target_name)

					if len(target_names) > 0:
						f.write("build %s: phony " % cfg_name)
						for tname in target_names:
							f.write("%s " % ( N.GetTargetPath(tname, cfg)))
						f.write("\n")
			f.write("\n")






			# for arch in archs:
			# 	f.write("%s " % N.GetTargetName(cfg_default, arch))
			# f.write("\n\n")
			# for cfg_name in N.configs:
			# 	if cfg_name != DEFAULT_NAME:
			# 		cfg = N.configs[cfg_name];
			# 		f.write("build %s: phony " % cfg_name)
			# 		for arch in archs:
			# 			f.write("%s " % N.GetTargetName(cfg, arch))
			# 		f.write("\n\n")


			f.write("build all: phony ");
			for target_name in N.all_targets:
				cfg = N.configs[target_name]
				f.write("%s " % target_name)
			f.write("\n\n")

			f.write("default build.ninja %s\n\n" % (N.GetTargetPath(N.default_target, cfg_default)))

			# for cfg_name in N.configs:
			# 	if cfg_name != DEFAULT_NAME:
			# 		cfg = N.configs[cfg_name];
			# 		for arch in archs:
			# 			f.write("%s " % N.GetTargetName(cfg, arch))
			# f.write("\n\n")
			# if hasattr(N.active_module, 'WriteCustomRules'):
			# 	N.active_module.WriteCustomRules(N, f)



N = NGen()
N.Run()


