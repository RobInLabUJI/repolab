#!/usr/bin/env python

import os, sys, yaml

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
                      'cuda': ['9.0', '9.1', '9.2', '10.0'],
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
            print("CUDA version %s not supported. Valid options are: %s" % (version,  SUPPORTED_VERSIONS['cuda']))
            sys.exit(1)
    except KeyError:
        cuda_version = None
    try:
        opengl_option = str(base['opengl'])
        if not opengl_option in SUPPORTED_VERSIONS['opengl']:
            print("OpenGL option %s not supported. Valid options are: %s" % (version,  SUPPORTED_VERSIONS['opengl']))
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

RUN apt-get update && apt-get -yq dist-upgrade \
 && apt-get install -yq --no-install-recommends \
	locales python-pip \
	python3-pip python3-setuptools git build-essential \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*

RUN pip3 install jupyterlab bash_kernel \
 && python3 -m bash_kernel.install

ENV SHELL=/bin/bash \
	NB_USER=jovyan \
	NB_UID=1000 \
	LANG=en_US.UTF-8 \
	LANGUAGE=en_US.UTF-8

ENV HOME=/home/${NB_USER}

RUN adduser --disabled-password \
	--gecos "Default user" \
	--uid ${NB_UID} \
	${NB_USER}

EXPOSE 8888
WORKDIR ${HOME}

CMD ["jupyter", "lab", "--no-browser", "--ip=0.0.0.0", "--NotebookApp.token=''"]

USER ${NB_USER}
"""

def main():
    os.chdir(PROJECT_DIR)
    yaml_file = read_yaml_file()
    base_image = get_base_image(yaml_file)
    
    with open(DOCKER_FILE, "w") as dockerfile:
        dockerfile.write("FROM %s\n" % base_image)
        dockerfile.write(DOCKER_JUPYTERLAB)
        
    with open(BUILD_FILE, "w") as scriptfile:
        scriptfile.write("#!/bin/sh\ndocker build -f %s -t %s ." % (DOCKER_FILE, yaml_file['name']))
    os.chmod(BUILD_FILE, 0o755)
    
    with open(RUN_FILE, "w") as scriptfile:
        scriptfile.write("#!/bin/sh\ndocker run --rm -p 8888:8888 %s" % (yaml_file['name']))
    os.chmod(RUN_FILE, 0o755)
    
if __name__ == "__main__":
    main()