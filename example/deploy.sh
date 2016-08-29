#!/usr/bin/env bash

virtualenv env

./env/bin/pip install ..

virtualenv --relocatable env

mkdir -p lib

rsync -av --delete --delete-excluded\
    --exclude="*.dist-info" \
    --exclude="*.egg-info" \
    --exclude="*.pyc" \
    --exclude="_*" \
    --exclude="pip" \
    --exclude="setuptools" \
    --exclude="wheel" \
    --exclude="pkg_resources" \
    --exclude="*.so" \
    --exclude="*.dll" \
    --include="*.py" \
    env/lib/python*/site-packages/ lib

cd lib

for package in *;
    do zip -r ${package}.zip ${package} && rm -fr ${package}
done

cd -

rm -fr env