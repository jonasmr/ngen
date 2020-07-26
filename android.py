#!/usr/bin/python
import os
import shutil


def FixupFile(Fixups, Path):
	lines = []
	with open(Path, "r") as File:
		for line in File:
			lines.append(line)
	with open(Path, "w") as File:
		for line in lines:
			for fix in Fixups:
				line = line.replace(fix, Fixups[fix])
			File.write(line)

def RegisterActions(N):
	N.parser.add_argument('--android-setup', help='setup android shit', action="store_true")

def ExecuteActions(N):
	if N.args.android_setup:
		srcpath = os.path.join(N.code_path, "android-template")
		dstpath = os.path.join(N.outdir, "android/android-project")
		print("paths %s :: %s\n" %(srcpath, dstpath))
		shutil.rmtree(dstpath, ignore_errors=True)
		shutil.copytree(srcpath, dstpath)
		BuildGradlePath = os.path.join(dstpath, "app/build.gradle")
		AndroidManifestPath = os.path.join(dstpath, "app/src/main/AndroidManifest.xml")
		StringsPath = os.path.join(dstpath, "app/src/main/res/values/strings.xml")
		Fixups = {}
		Fixups["%app%"] = N.android_app
		Fixups["%package%"] = N.android_package
		Fixups["%lib%"] = N.GetConfig("").target

		FixupFile(Fixups, BuildGradlePath)
		FixupFile(Fixups, AndroidManifestPath)
		FixupFile(Fixups, StringsPath)
		return False #just continue
	return False

def UpdateAndroidVersion(N):
	N.android_sdk = "%sndk/%s" % (N.android_sdk_root, N.android_version)
	N.android_toolchain = N.android_sdk + "/toolchains/llvm/prebuilt/%s" % N.android_llvm_platform
	N.android_bin = N.android_toolchain + "/bin"

def Init(N):
	N.android_sdk_root = os.environ["ANDROID_SDK_ROOT"]
	N.archs = {"armv7":{},"aarch64":{},"x86":{},"x86_64":{}}
	N.android_version = "21.0.6113669"
	N.android_host_platform = "linux"
	if N.host_platform == "linux":
		N.android_llvm_platform = "linux-x86_64"
	elif N.host_platform == "osx":
		N.android_llvm_platform = "darwin-x86_64"
	else:
		print("please fix platform")
	UpdateAndroidVersion(N)


def PreMerge(N):
	UpdateAndroidVersion(N)
	N.ProcessFile1("%s/sources/android/native_app_glue/android_native_app_glue.c" % N.android_sdk)

def HandleCommand(N, command, arg, cfg):
	if command == "android_package":
		N.android_package = arg
		return True
	elif command == "android_app":
		N.android_app = arg
		return True
	elif command == "android_version":
		N.android_version = arg
		UpdateAndroidVersion(N)
		return True

	return False

def WriteAssignments(N, f):
	f.write("c = " + N.android_bin + "/clang \n")
	f.write("cxx = " + N.android_bin + "/clang++ \n")
	f.write("link = " + N.android_bin + "/clang++ \n")
	f.write("ar = " + N.android_bin + "/arm-linux-androideabi-ar \n")
	f.write("ranlib = " + N.android_bin + "/arm-linux-androideabi-ranlib \n")
	f.write("\n")
	f.write("android_toolchain_args = --gcc-toolchain=%s --sysroot=%s/sysroot -I%s/sources/android/native_app_glue" %(N.android_toolchain, N.android_toolchain, N.android_sdk))
	f.write("\n\n")




def GetABIFolder(arch):
	if arch == "armv7":
		return "armeabi-v7a"
	#todo: none of the ones below are tested
	elif arch == "aarch64":
		return "aarch64"
	elif arch == "x86":
		return "x86"
	elif arch == "x86_64":
		return "x86_64"
	else:
		print("unknown arch!\n")
		exit(1)

def WriteCustomRules(N, f):
	f.write("#android custom rules\n\n")

	f.write("deploy-bin = $outdir/android-project/app/src/main/jniLibs\n\n")
	archs = N.archs
	if len(archs) == 0:
		archs = {"":""}
	for cfg_name in N.configs:
		if cfg_name != "__default":
			cfg = N.configs[cfg_name];
			f.write("rule deploy_%s\n  command = " % cfg_name)
			for arch in archs:
				arch_suffix = N.GetArchSuffix(arch)
				target_name = N.GetTargetName(cfg, arch)
				f.write("mkdir -p $deploy-bin/%s/ && " % (GetABIFolder(arch)))
				f.write("cp %s $deploy-bin/%s/lib%s.so && " % (N.GetTargetName(cfg, arch), GetABIFolder(arch), N.target))
			f.write("cd $outdir/android-project && ")
			f.write("./gradlew installDebug")
			f.write("\n\n")


	for cfg_name in N.configs:
		if cfg_name != "__default":
			cfg = N.configs[cfg_name];
			f.write("build $tempdir/android/deploy_dummy_%s: deploy_%s " % (cfg_name, cfg_name))
			for arch in archs:
				arch_suffix = N.GetArchSuffix(arch)
				f.write("%s " % N.GetTargetName(cfg, arch))
			f.write("\n")

	f.write("\n")

	for cfg_name in N.configs:
		if cfg_name != "__default":
			cfg = N.configs[cfg_name];
			if cfg_name == N.default_config:
				f.write("build deploy: phony $tempdir/android/deploy_dummy_%s\n" % cfg_name)
			f.write("build deploy_%s: phony $tempdir/android/deploy_dummy_%s\n" % (cfg_name,cfg_name))


def Extension(N):
	return ".so"


