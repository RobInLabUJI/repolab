#!/usr/bin/env python

import os, sys, yaml
import os.path

PROJECT_DIR  = '/project'
PROJECT_FILE = 'repolab.yaml'
DOCKER_FILE  = 'repolab.dockerfile'
BUILD_FILE   = 'repolab_build.sh'
RUN_FILE     = 'repolab_run.sh'

def read_yaml_file():
    try:
        with open(PROJECT_FILE, 'r') as stream:
            try:
                yaml_file = yaml.load(stream)
            except yaml.YAMLError as e:
                print(e)
                sys.exit(1)
    except FileNotFoundError:
        print("File '%s' not found in folder '%s'" % (PROJECT_FILE, PROJECT_DIR))
        sys.exit(1)
    return yaml_file

SUPPORTED_SYSTEMS = ['ubuntu', 'centos']
SUPPORTED_VERSIONS = {'ubuntu': ['16.04', '18.04'], 
                      'centos': ['7'],
                      'cuda': ['8.0', '9.0', '9.1', '9.2', '10.0'],
                      'opengl': ['runtime', 'devel']}

def get_base_image(yaml_file):
    try:
        base = yaml_file['base']
        try:
            system = base['system'].lower()
            version = str(base['version'])
        except KeyError as e:
            print("Key %s not found in base: %s" % (e, base))
            sys.exit(1)
    except KeyError as e:
        print("Key %s not found in file %s" % (e, PROJECT_FILE) )
        sys.exit(1)
    if not system in SUPPORTED_SYSTEMS:
        print("System %s is not supported. Valid options are: %s" % (system, SUPPORTED_SYSTEMS))
        sys.exit(1)
    if not version in SUPPORTED_VERSIONS[system]:
        print("Version %s not supported in %s system. Valid options are: %s" % (version, system, SUPPORTED_VERSIONS[system]))
        sys.exit(1)
    try:
        cuda_version = str(base['cuda'])
        if not cuda_version in SUPPORTED_VERSIONS['cuda']:
            print("CUDA version %s not supported. Valid options are: %s" % (cuda_version,  SUPPORTED_VERSIONS['cuda']))
            sys.exit(1)
    except KeyError:
        cuda_version = None
    try:
        opengl_option = str(base['opengl'])
        if not opengl_option in SUPPORTED_VERSIONS['opengl']:
            print("OpenGL option %s not supported. Valid options are: %s" % (opengl_option,  SUPPORTED_VERSIONS['opengl']))
            sys.exit(1)
    except KeyError:
        opengl_option = None
    if cuda_version and opengl_option:
        base_image = 'nvidia/cudagl:' + cuda_version + '-devel-' + system + version
    elif cuda_version:
        base_image = 'nvidia/cuda:' + cuda_version + '-cudnn7-devel-' + system + version
    elif opengl_option:
        base_image = 'nvidia/opengl:1.0-glvnd-devel-' + system + version
    else:
        base_image = system + ':' + version
    return base_image
        
DOCKER_JUPYTERLAB = """
ENV DEBIAN_FRONTEND noninteractive
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8

RUN apt-get update && apt-get -yq dist-upgrade \\
 && apt-get install -yq --no-install-recommends \\
	locales python-pip cmake \\
	python3-pip python3-setuptools git build-essential \\
 && apt-get clean \\
 && rm -rf /var/lib/apt/lists/*

RUN pip3 install jupyterlab bash_kernel \\
 && python3 -m bash_kernel.install

ENV SHELL=/bin/bash \\
	NB_USER=jovyan \\
	NB_UID=1000 \\
	LANG=en_US.UTF-8 \\
	LANGUAGE=en_US.UTF-8

ENV HOME=/home/${NB_USER}

RUN adduser --disabled-password \\
	--gecos "Default user" \\
	--uid ${NB_UID} \\
	${NB_USER}

EXPOSE 8888
WORKDIR ${HOME}

CMD ["jupyter", "lab", "--no-browser", "--ip=0.0.0.0", "--NotebookApp.token=''"]
"""

BUILD_SCRIPT = """#!/bin/sh
docker build -f %s -t %s ."""

RUN_SCRIPT   = """#!/bin/sh
docker run --rm -p 8888:8888 %s"""

NVIDIA_RUN_SCRIPT = """#!/bin/sh
XAUTH=/tmp/.docker.xauth
if [ ! -f $XAUTH ]
then
    xauth_list=$(xauth nlist :0 | sed -e 's/^..../ffff/')
    if [ ! -z "$xauth_list" ]
    then
        echo $xauth_list | xauth -f $XAUTH nmerge -
    else
        touch $XAUTH
    fi
    chmod a+r $XAUTH
fi
docker run --rm \\
    --env="DISPLAY" \\
    --env="QT_X11_NO_MITSHM=1" \\
    --volume="/tmp/.X11-unix:/tmp/.X11-unix:rw" \\
    --env="XAUTHORITY=$XAUTH" \\
    --volume="$XAUTH:$XAUTH" \\
    --runtime=nvidia \\
    -p 8888:8888 %s"""

def is_nvidia(base_image):
    return base_image[:6] == "nvidia"

DOCKER_APT = """
RUN apt-get update \\
 && apt-get install -yq --no-install-recommends \\
%s && apt-get clean \\
 && rm -rf /var/lib/apt/lists/*
"""

def apt_packages(yaml_file):
    if 'apt-packages' in yaml_file.keys():
        pstr = ''
        for p in yaml_file['apt-packages']:
            pstr += '    ' + p + ' \\\n'
        return DOCKER_APT % pstr
    else:
        return ''

DOCKER_CMAKE = """
RUN git clone %s /%s \\
 && cd /%s \\
 && mkdir build \\
 && cd build \\
 && cmake .. \\
 && make -j2 install \\
 && rm -fr /%s
"""

def source_packages(yaml_file):
    if 'source-packages' in yaml_file.keys():
        sstr = ''
        for p in yaml_file['source-packages']:
            if 'depends' in p.keys() and p['depends']:
                dstr = ''
                for d in p['depends']:
                    dstr += '    ' + d + ' \\\n'
                sstr += DOCKER_APT % dstr
            sstr += DOCKER_CMAKE % (p['repo'], p['name'], p['name'], p['name'])
        return sstr
    else:
        return ''

DOCKER_COPY_REPO = """
COPY . ${HOME}
RUN chown -R ${NB_UID} ${HOME}
USER ${NB_USER}
"""

DOCKER_BUILD_REPO = """
RUN mkdir build \\
 && cd build \\
 && cmake .. \\
 && make -j2
"""

DOCKER_IGNORE_FILE = ".dockerignore"

DOCKER_IGNORE_CONTENTS = """README.md
%s
%s
%s
%s
%s
""" % (DOCKER_IGNORE_FILE, PROJECT_FILE, DOCKER_FILE, BUILD_FILE, RUN_FILE)

NOTEBOOK_TAIL = """
 "metadata": {
  "kernelspec": {
   "display_name": "Bash",
   "language": "bash",
   "name": "bash"
  },
  "language_info": {
   "codemirror_mode": "shell",
   "file_extension": ".sh",
   "mimetype": "text/x-sh",
   "name": "bash"
  }
 },
 "nbformat": 4,
 "nbformat_minor": 2
}
"""
def custom_commands(yaml_file):
    s = ''
    for c in yaml_file['custom']:
        s += "RUN " + c + "\n"
    return s
    
def main():
    os.chdir(PROJECT_DIR)
    yaml_file = read_yaml_file()
    base_image = get_base_image(yaml_file)
    
    with open(DOCKER_FILE, "w") as dockerfile:
        dockerfile.write("FROM %s\n" % base_image)
        dockerfile.write(DOCKER_JUPYTERLAB)
        dockerfile.write(apt_packages(yaml_file))
        dockerfile.write(source_packages(yaml_file))
        dockerfile.write(DOCKER_COPY_REPO)
        if 'custom' in yaml_file.keys():
            dockerfile.write(custom_commands(yaml_file))
        else:
            dockerfile.write(DOCKER_BUILD_REPO)

    with open(BUILD_FILE, "w") as scriptfile:
        scriptfile.write(BUILD_SCRIPT % (DOCKER_FILE, yaml_file['name']))
    os.chmod(BUILD_FILE, 0o755)
    
    with open(RUN_FILE, "w") as scriptfile:
        if is_nvidia(base_image):
            run_script = NVIDIA_RUN_SCRIPT
        else:
            run_script = RUN_SCRIPT
        scriptfile.write(run_script % (yaml_file['name']))
    os.chmod(RUN_FILE, 0o755)
    
    with open(DOCKER_IGNORE_FILE, "w") as ignorefile:
        ignorefile.write(DOCKER_IGNORE_CONTENTS)
    
    if os.path.isfile("README.md"):
        os.system("notedown README.md | head -n -4 > README.ipynb")
        with open("README.ipynb", "a") as myfile:
            myfile.write(NOTEBOOK_TAIL)
            
if __name__ == "__main__":
    main()
