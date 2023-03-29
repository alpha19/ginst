'''
ginst.py - A script to make/install/download GCC

MIT License - Charles Machalow
'''
import ftplib
import logging
import multiprocessing
import os
import re
import shutil
import subprocess
import sys
import argparse

try:
    raw_input
except:
    raw_input = input

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
ch.setFormatter(formatter)
logger.addHandler(ch)

THIS_FOLDER = os.path.abspath(os.path.dirname(__file__))

GCC_LOCAL_COMPRESSED_SOURCE_PATH = os.path.join(THIS_FOLDER, 'gcc.tar.gz')
GCC_SOURCE_URL = "http://ftpmirror.gnu.org/gcc/gcc-%s/gcc-%s.tar.gz"
GCC_FTP_BASE = 'mirrors.ocf.berkeley.edu'
GCC_FTP_VERSION_FOLDER = 'gnu/gcc'
GCC_FTP_REGEX = r'%s/gcc\-(\d?\.\d*\.\d*)$' % GCC_FTP_VERSION_FOLDER

class GccVersion(object):
    def __init__(self, versionString, extraConfigureArgs=''):
        if isinstance(versionString, (str, bytes)):
            self.rawVersionString = versionString
        else:
            raise AttributeError("versionString should be string-like")

        self.extraConfigureArgs = extraConfigureArgs

    @classmethod
    def getPossibleGccVersions(cls):
        retList = []
        f = ftplib.FTP(GCC_FTP_BASE)
        f.login()
        listing = f.nlst(GCC_FTP_VERSION_FOLDER)
        for i in listing:
            matches = re.findall(GCC_FTP_REGEX, i)
            if matches:
                retList.append(matches[0])
        return retList

    @classmethod
    def selectGccVersion(cls):
        pStr = 'Select a gcc version to compile and install...\n'
        versions = cls.getPossibleGccVersions()
        for idx, itm in enumerate(versions):
            idx = idx + 1
            pStr += '%-3d) %-10s' % (idx, itm)
            if idx % 5 == 0:
                pStr += '\n'
        pStr += '\nSelection (q to quit): '
        while True:
            try:
                choice = raw_input(pStr)
                if choice == 'q':
                    sys.exit(-1)
                if int(choice) <= idx:
                    return versions[int(choice) - 1]
            except Exception as ex:
                if isinstance(ex, (SystemExit, KeyboardInterrupt)):
                    raise

    def getSourceUrl(self):
        return GCC_SOURCE_URL % (self.rawVersionString, self.rawVersionString)

    def getLocalUncompressedSourcePath(self):
        return os.path.join(THIS_FOLDER, 'gcc-%s' % self.rawVersionString)

    def getLocalBuildPath(self):
        return os.path.join(self.getLocalUncompressedSourcePath(), 'build')

    def getConfigureCommand(self):
        if SystemCall.hasRoot():
            prefix = '/usr/local/'
        else:
            prefix = os.path.expanduser('~/')

        return self.getLocalUncompressedSourcePath() + \
        "/configure -v --with-system-zlib --build=x86_64-linux-gnu --host=x86_64-linux-gnu --target=x86_64-linux-gnu --prefix=%sgcc-%s --enable-checking=release --enable-languages=c,c++ --enable-multilib --program-suffix=-%s %s" \
        % (prefix, self.rawVersionString, self.rawVersionString, self.extraConfigureArgs)

class SystemCall(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self._execute()

    def _execute(self):
        logger.debug("About to call %s" % self.cmd)
        self.output = ''
        self.process = subprocess.Popen(self.cmd, shell=True, stderr=subprocess.STDOUT, stdout=subprocess.PIPE)
        while self.process.returncode is None:
            self.process.poll()
            self.process.stdout.flush()
            line = self.process.stdout.readline().rstrip(os.linesep)
            logger.debug("| %s" % line)
            self.output += line

        self.retCode = self.process.returncode
        logger.debug("... return code: %d" % self.retCode)

    def succeeded(self):
        return self.retCode == 0

    def failed(self):
        return not self.succeeded()

    @classmethod
    def hasRoot(cls):
        logger.debug("Checking for root")
        return SystemCall('ls /root').succeeded()

class GInst(object):
    def __init__(self, gccVersion=None):
        os.chdir(THIS_FOLDER)
        if gccVersion is None:
            gccVersion = GccVersion.selectGccVersion()
        elif isinstance(gccVersion, GccVersion):
            self.gccVersion = gccVersion
        else:
            self.gccVersion = GccVersion(gccVersion)

    def _isAvailable(self, tool):
        logger.debug("checking if %s is available.." % tool)
        return SystemCall("which %s" % tool).succeeded()

    def _getGInstPreReqs(self):
        if SystemCall.hasRoot():
            logger.info("Getting pre-reqs to run this script")
            if SystemCall('apt-get update -y && apt-get upgrade -y').failed():
                raise EnvironmentError("Failed to apt-get update/upgrade")

            if SystemCall('apt-get install wget gcc g++ gcc-multilib g++-multilib build-essential libc6-dev zlib1g-dev flex bison texinfo automake -y').failed():
                raise EnvironmentError("Failed to get GInst prereqs")
        else:
            logger.warning("No root detected, skipping GInst pre-reqs... if this fails, run as root/sudo")

    def _downloadSource(self):
        logger.info("About to download the gcc source")
        if self._isAvailable('wget'):
            fail = True
            for i in range(5):
                logger.debug("wget try %d / %d" % (i + 1, 5))
                if SystemCall('curl -L %s -k > %s' % (self.gccVersion.getSourceUrl(), GCC_LOCAL_COMPRESSED_SOURCE_PATH)).succeeded():
                    fail = False
                    break
            if fail:
                raise EnvironmentError("Failed to wget the gcc source")
        else:
            raise EnvironmentError("wget was unavailable to download the gcc source")

    def _unCompressSource(self):
        logger.info("About to uncompress the gcc source")
        if not SystemCall('tar xf %s' % GCC_LOCAL_COMPRESSED_SOURCE_PATH).succeeded():
            raise EnvironmentError("Unable to untar gcc source")

    def _moveToUncompressedSourceFolder(self):
        logger.info("Moving to uncompressed source folder")
        os.chdir(self.gccVersion.getLocalUncompressedSourcePath())

    def _callDownloadPrereqs(self):
        logger.info("Calling contrib/download_prerequisites")
        if not SystemCall('contrib/download_prerequisites').succeeded():
            logger.warning("Unable to download prereqs via source script... that might be ok if this is an old gcc")

    def _makeAndEnterBuildDirectory(self):
        logger.info("Creating and entering the build directory")
        os.makedirs(self.gccVersion.getLocalBuildPath())
        os.chdir(self.gccVersion.getLocalBuildPath())

    def _configureBuild(self):
        logger.info("Calling configure")
        if not SystemCall(self.gccVersion.getConfigureCommand()).succeeded():
            raise EnvironmentError("Unable to configure the build")

    def _make(self):
        logger.info("Calling make... this will take a while")
        cpuCount = multiprocessing.cpu_count()
        makeCommand = 'make clean && make -j%d' % cpuCount
        if not SystemCall(makeCommand).succeeded():
            raise EnvironmentError("compilation via make failed")

    def _install(self):
        logger.info("Installing the new gcc")
        if not SystemCall('make install').succeeded():
            raise EnvironmentError("Unable to install the new gcc")

    def install(self):
        self._getGInstPreReqs()
        self._downloadSource()
        self._unCompressSource()
        self._moveToUncompressedSourceFolder()
        self._callDownloadPrereqs()
        self._configureBuild()
        self._make()
        self._install()
        logger.info("Done installing gcc")

    def installFromFolder(self, gccFolder):
        self._getGInstPreReqs()
        logger.info("Moving gcc to expected uncompressed source path folder")
        shutil.move(gccFolder, self.gccVersion.getLocalUncompressedSourcePath())
        self._moveToUncompressedSourceFolder()
        self._callDownloadPrereqs()
        self._configureBuild()
        self._make()
        self._install()
        logger.info("Done installing gcc")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('-g', '--gcc', help='Gcc version', default='12.2.0')
    args = parser.parse_args()
    
    g = GInst(args.gcc)
    g.install()
