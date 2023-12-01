#torch=1.13.1, cuda=11.7, python3.8 sacred 0.8.4

FROM nvidia/cuda:11.1.1-cudnn8-devel-ubuntu20.04
MAINTAINER Fanchao Xu

# CUDA includes
ENV CUDA_PATH /usr/local/cuda
ENV CUDA_INCLUDE_PATH /usr/local/cuda/include
ENV CUDA_LIBRARY_PATH /usr/local/cuda/lib64
ENV DEBIAN_FRONTEND=noninteractive

RUN if [ -f /etc/apt/sources.list.d/cuda.list ]; then rm /etc/apt/sources.list.d/cuda.list; fi
RUN if [ -f /etc/apt/sources.list.d/nvidia-ml.list ]; then rm /etc/apt/sources.list.d/nvidia-ml.list; fi

# Ubuntu Packages
RUN apt-get update -y && apt-get install software-properties-common -y && \
    add-apt-repository -y multiverse && apt-get update -y && apt-get upgrade -y && \
    apt-get install -y apt-utils nano vim man build-essential wget sudo && \
    rm -rf /var/lib/apt/lists/*

# Install curl and other dependencies
RUN apt-get update -y && apt-get install -y curl libssl-dev openssl libopenblas-dev \
    libhdf5-dev hdf5-helpers hdf5-tools libhdf5-serial-dev libprotobuf-dev protobuf-compiler git


# Install python3 pip3
RUN echo 'tzdata tzdata/Areas select Etc' | debconf-set-selections && \
    echo 'tzdata tzdata/Zones/Etc select UTC' | debconf-set-selections

RUN apt-get update
RUN apt-get -y install python3.8
RUN apt-get -y install python3-pip
RUN pip3 install --upgrade pip


# Set the working directory in the container
WORKDIR /pymarl

# Copy the contents of your project into the container
COPY . /pymarl

# Install your project
RUN python3 setup.py install

# Modify the PyTorch _six.py file
RUN echo 'import collections.abc as container_abcs' >> /opt/conda/lib/python3.8/site-packages/torch/_six.py \
 && echo 'int_classes = int' >> /opt/conda/lib/python3.8/site-packages/torch/_six.py

### -- SMAC
ENV SC2PATH /pymarl/3rdparty/StarCraftII
