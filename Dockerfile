FROM python:3

RUN pip install pyyaml notedown

RUN mkdir /project

ADD repolab_create.py /

CMD [ "python", "repolab_create.py" ]
