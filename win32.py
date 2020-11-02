#!/usr/bin/python
import os
import shlex
import subprocess

def RunVSWhere(N, ExtraArgs):
	Result = {}
	if N.active_platform == "win32":
		ProgramFilesx84 = os.getenv("ProgramFiles(x86)");
		Path = "\"%s\\Microsoft Visual Studio\\Installer\\vswhere.exe\"%s" % (ProgramFilesx84, ExtraArgs);
		print(shlex.split(Path))
		Process = subprocess.Popen(args=shlex.split(Path), stdout=subprocess.PIPE)
		out, err = Process.communicate()
		Process.wait()
		lines = out.splitlines()
		for line in lines:
			l = line.decode('utf-8')
			l = l.strip()
			idx = l.find(":")
			if idx > 0:
				key = l[:idx]
				value = l[idx+2:]
				Result[key] = value
	return Result;

def RegisterActions(N):
	pass

def ExecuteActions(N):
	return False

def Init(N):
	N.g_win32sdk = ""
	N.g_win32InstallationPath = ""
	N.g_win32VersionPath = ""
	N.g_win32VCVersionNumber = ""
	N.g_win32sdkInclude = ""
	N.g_win32sdkLib = ""
	N.g_win32CLPath = "";
	N.g_win32LinkPath = "";
	N.g_win32VCPath = ""
	N.g_vswhere = {}
	if N.active_platform == "win32":
		N.g_vswhere = RunVSWhere(N, " -products 'Microsoft.VisualStudio.Product.BuildTools'")
		if not "installationPath" in N.g_vswhere:
			N.g_vswhere = RunVSWhere(N, "")
		N.g_win32InstallationPath = N.g_vswhere["installationPath"]
		N.g_win32VersionPath = "%s\\VC\\Auxiliary\\Build\\Microsoft.VCToolsVersion.default.txt" % N.g_win32InstallationPath
		with open(N.g_win32VersionPath) as f:
			N.g_win32VCVersionNumber = ''.join(f.read().split())
		N.g_win32CLPath = "%s\\VC\\Tools\\MSVC\\%s\\bin\\HostX64\\x64\\cl.exe" % (N.g_win32InstallationPath, N.g_win32VCVersionNumber)
		N.g_win32LinkPath = "%s\\VC\\Tools\\MSVC\\%s\\bin\\HostX64\\x64\\link.exe" % (N.g_win32InstallationPath, N.g_win32VCVersionNumber)
		N.g_win32VCPath = "%s\\VC\\Tools\\MSVC\\%s" % (N.g_win32InstallationPath, N.g_win32VCVersionNumber)

def PreMerge(N):
	if N.g_win32sdk != "":
		N.g_win32sdkInclude = "C:\\Program Files (x86)\\Windows Kits\\10\\Include\\%s" % N.g_win32sdk
		N.g_win32sdkLib = "C:\\Program Files (x86)\\Windows Kits\\10\\Lib\\%s" % N.g_win32sdk
		N.AddParam("cflags", "-I\"%s\\include\"" % N.g_win32VCPath)
		N.AddParam("cflags", "-I\"%s\\atlmfc\\include\"" % N.g_win32VCPath)
		N.AddParam("cflags", "-I\"%s\\ucrt\"" % N.g_win32sdkInclude)
		N.AddParam("cflags", "-I\"%s\\um\"" % N.g_win32sdkInclude)
		N.AddParam("cflags", "-I\"%s\\shared\"" % N.g_win32sdkInclude)
		N.AddParam("ldflags", "/LIBPATH:\"%s\\ucrt\\x64\"" % N.g_win32sdkLib);
		N.AddParam("ldflags", "/LIBPATH:\"%s\\um\\x64\"" % N.g_win32sdkLib);
		N.AddParam("ldflags", "/LIBPATH:\"%s\\lib\\x64\"" % N.g_win32VCPath)

def HandleCommand(N, command, arg, cfg):
	if command == "win32sdk":
		N.g_win32sdk = arg
		print("win32 SDK: " + N.g_win32sdk)
		return True
	endif
	return False

def WriteAssignments(N, f):
	f.write("cxx = " + N.g_win32CLPath + "\n\n")
	f.write("link = " + N.g_win32LinkPath + "\n\n")

def Extension(N):
	return ".exe"



