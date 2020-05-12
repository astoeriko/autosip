# autosip

This script automates the start of spectral induced polarization (SIP) measurements with the Ontash & Ermac PSIP TOOL software.
It has been tested with the instrument of the Ecohydrology lab at the University of Waterloo and of the Hydrogeology group at the University of Tübingen.
It interacts with the SIP software by creating HTTP post requests that contain the information that is otherwise entered manually into the form of the web interface.

## Requirements and Installation
The script is based on Python 3.7 and requires the packages `requests` and `arrow`.
I recommend installing these dependencies with [`conda`](https://docs.conda.io/en/latest/index.html):
```
conda install arrow requests
```
You can also install into a new environment with
```
conda create -n env arrow requests 
```
where `env` is the name of the environment.
Then activate the environment with
```
conda activate env
```
before running the script.

To install the script itself you simply need to clone this repository or download the source code.
For cloning with git do:
```
git clone https://github.com/astoeriko/autosip.git
```

## Usage
The script is run from the command line.

### Command line arguments
There are several command line options that can be shown with:
```
python autosip.py --help
```

### Parameter Files
Before running the script you need to create a file that describes the mapping of stimulus channels to response channels.
The mapping needs to be specified in JSON format.
For example, you could inject current in stimulus channel 1 and sense the corresponding response in response channels 1 and 2.
If you additionally want to inject current in channel 2 and measure in channels 3 and 4, the mapping file could look like this:
```
{
	"1": [1, 2],
	"2": [3, 4]
}
```

A second file specifies the parameters for each SIP run (frequency range, number of steps,...).
It should also be given in JSON format.
Examples can be found in this repository.

### Running the script
The command for running the script could look like this:
```
python autosip.py --paramfile parameters.json --channels-file channel_mapping.json --basename experiment_xy --interval "1:00" --ip XXX.XXX.XXX.XXX --measure-full-hours --measure-full-hours
```
This assumes that the script is run from the directory where it is stored and that parameter files are stored in the same location.
If you want to run the script from a different folder or the parameter files are stored elsewhere, specify full paths to the script or parameter files

When specifying version 1.3.1h-1 for the PSIP software, you will be prompted for authentication data to acces the SIP server.
