#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AUTHOR
    - Antti Suni <antti.suni@helsinki.fi>
    - Sébastien Le Maguer <slemaguer@coli.uni-saarland.de>

DESCRIPTION

usage: cwt_analysis_synthesis.py [-h] [-v] [-M MODE] [-m MEAN_F0] [-o OUTPUT]
                                 [-P]
                                 input_file

Tool for CWT analysis/synthesis of the F0

positional arguments:
  input_file            Input signal or F0 file

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbosity       increase output verbosity
  -M MODE, --mode MODE  script mode: 0=analysis, 1=synthesis, 2=analysis/synthesis
  -m MEAN_F0, --mean_f0 MEAN_F0
                        Mean f0 needed for synthesis (unsed for analysis modes)
  -o OUTPUT, --output OUTPUT
                        output directory for analysis or filename for synthesis.
                        (Default: input_file directory [Analysis] or <input_file>.f0 [Synthesis])
  -P, --plot            Plot the results


LICENSE
    See LICENSE
"""

import sys
import os
import traceback
import argparse
import time
import logging

import yaml

# Collections
from collections import defaultdict

import warnings

import pylab

# Wavelet import
from wavelet_prosody_toolkit.prosody_tools import misc
from wavelet_prosody_toolkit.prosody_tools import cwt_utils
from wavelet_prosody_toolkit.prosody_tools import f0_processing

import numpy as np

# List of logging levels used to setup everything using verbose option
LEVEL = [logging.WARNING, logging.INFO, logging.DEBUG]


# FIXME: be more specific!
warnings.simplefilter("ignore", np.ComplexWarning) # Plotting can't deal with complex, but we don't care


###############################################################################
# Functions
###############################################################################
def load_f0(input_file, configuration):
    """Load the f0 from a text file or extract it from a wav file

    Parameters
    ----------
    input_file: string
        The input file name.

    Returns
    -------
    1D arraylike
       the raw f0 values
    """
    if input_file.lower().endswith(".f0"):
        raw_f0 = np.loadtxt(input_file)
    elif input_file.lower().endswith(".wav"):
        logging.info("Extracting the F0 from the signal")
        (fs, wav_form) = misc.read_wav(input_file)
        raw_f0 = f0_processing.extract_f0(wav_form, fs)

    return raw_f0


###############################################################################
# Main function
###############################################################################
def run():
    """Main entry function

    This function contains the code needed to achieve the analysis and/or the synthesis
    """
    global args

    # Loading default configuration
    with open(os.path.dirname(os.path.realpath(__file__)) + "/configs/default.yaml", 'r') as f:
        configuration = defaultdict(lambda: False, yaml.load(f))

    # Loading user configuration
    if args.configuration_file:
        try:
            with open(args.configuration_file, 'r') as f:
                configuration = defaultdict(lambda: False, yaml.load(f))
        except IOError as ex:
            logging.error("configuration file " + args.config + " could not be loaded:")
            logging.error(ex.msg)
            sys.exit(1)

    # Dealing with output
    output_dir = args.output_file
    if output_dir is None:
        output_dir = os.path.dirname(args.input_file)
    basename = os.path.basename(args.input_file)
    output_file = os.path.join(output_dir, basename)

    scales = None

    # Analysis
    if (args.mode % 2) == 0:
        raw_f0 = load_f0(args.input_file, configuration)
        logging.debug(raw_f0)

        logging.info("Processing f0")
        f0 = f0_processing.process(raw_f0)
        if args.plot:
            pylab.title("F0 preprocessing and interpolation")
            pylab.plot(f0, color="red", alpha=0.5, linewidth=3)
            pylab.plot(raw_f0, color="gray", alpha=0.5)

        logging.info("writing interpolated lf0\t" + output_file + ".interp")
        np.savetxt(output_file + ".interp", f0.astype('float'),
                   fmt="%f", delimiter="\n")

        # Perform continuous wavelet transform of mean-substracted f0 with 12 scales, one octave apart
        scales, widths, _ = cwt_utils.cwt_analysis(f0-np.mean(f0), num_scales=configuration["wavelet"]["num_scales"],
                                                   scale_distance=configuration["wavelet"]["scale_distance"],
                                                   mother_name=configuration["wavelet"]["mother_wavelet"],
                                                   apply_coi=False)

        # SSW parameterization, adjacent scales combined (with extra scales to handle long utterances)
        scales = cwt_utils.combine_scales(scales,
                                          [(0, 2), (2, 4), (4, 6), (6, 8), (8, 12)])
        for i in range(0, len(scales)):
            logging.debug("Mean scale[%d]: %s" % (i, str(np.mean(scales[i]))))

        logging.info("writing wavelet matrix \"%s.cwt\"" % output_file)
        np.savetxt(output_file + ".cwt", scales[:].T.astype('float'),
                   fmt="%f", delimiter="\n")

        # for individual training of scales
        for i in range(0, len(scales)):
            logging.info("writing scale \"%s.cwt.%d\"" % (output_file, i))
            np.savetxt("%s.cwt.%d" % (output_file, i+1),
                       scales[i].astype('float'),
                       fmt="%f", delimiter="\n")

    # then add deltas etc, train and generate
    # then synthesis by the following, voicing and mean value
    # have to come from other sources

    # Synthesis mode
    if args.mode >= 1 or args.plot:
        if scales is None:
            scales = np.loadtxt(args.input_file).reshape(-1, 5).T
        if args.mode == 1:
            rec = cwt_utils.cwt_synthesis(scales, args.mean_f0)
        else:
            rec = cwt_utils.cwt_synthesis(scales, np.mean(f0))
        # rec = exp(cwt_utils.cwt_synthesis(scales)+mean(lf0))
        # rec[f0==0] = 0

    if args.mode >= 1:
        if args.mode == 1:
            if output_file is None:
                output_file = args.input_file + "_rec.f0"
            else:
                output_file = args.output_file
        else:
            output_file += "_rec.f0"

        logging.info("Save reconstructed f0 in %s" % output_file)
        np.savetxt(output_file, rec.astype('float'), fmt="%f", delimiter="\n")

    if args.plot:
        pylab.figure()
        pylab.title("CWT decomposition to 5 scales and reconstructed signal")
        pylab.plot(rec, linewidth=5, color="blue", alpha=0.3)

        if (args.mode % 2) == 0:
            pylab.plot(f0, linewidth=1, color="red")

        for i in range(0, len(scales)):
            pylab.plot(scales[len(scales)-i-1]+max(rec)*1.5+i*75,
                       color="blue", alpha=0.5, linewidth=2)

        pylab.show()


###############################################################################
#  Envelopping
###############################################################################
def main():
    """Entry point for CWT analysis/synthesis tool

    This function is a wrapper to deal with arguments and logging.
    """
    global args

    try:
        parser = argparse.ArgumentParser(description="Tool for CWT analysis/synthesis of the F0")

        # Add options
        parser.add_argument("-c", "--configuration-file", default=None, help="configuration file")
        parser.add_argument("-M", "--mode", type=int, default=0,
                            help="script mode: 0=analysis, 1=synthesis, 2=analysis/synthesis")
        parser.add_argument("-m", "--mean_f0", type=float, default=100,
                            help="Mean f0 needed for synthesis (unsed for analysis modes)")
        parser.add_argument("-P", "--plot", action="store_true",
                            help="Plot the results")
        parser.add_argument("-v", "--verbosity", action="count", default=0,
                            help="increase output verbosity")

        # Add arguments
        parser.add_argument("input_file", help="Input signal or F0 file")
        parser.add_argument("output_file",
                            help="output directory for analysis or filename for synthesis. (Default: input_file directory [Analysis] or <input_file>.f0 [Synthesis])")

        # Parsing arguments
        args = parser.parse_args()

        # Verbose level => logging level
        log_level = args.verbosity
        if (args.verbosity > len(LEVEL)):
            logging.warning("verbosity level is too high, I'm gonna assume you're taking the highes ")
            log_level = len(LEVEL) - 1
        logging.basicConfig(level=LEVEL[log_level])

        # Debug time
        start_time = time.time()
        logging.info("start time = " + time.asctime())

        # Running main function <=> run application
        run()

        # Debug time
        logging.info("end time = " + time.asctime())
        logging.info('TOTAL TIME IN MINUTES: %02.2f' %
                     ((time.time() - start_time) / 60.0))

        # Exit program
        sys.exit(0)
    except KeyboardInterrupt as e:  # Ctrl-C
        raise e
    except SystemExit as e:  # sys.exit()
        pass
    except Exception as e:
        logging.error('ERROR, UNEXPECTED EXCEPTION')
        logging.error(str(e))
        traceback.print_exc(file=sys.stderr)
        sys.exit(-1)


if __name__ == '__main__':
    main()

# cwt_analysis_synthesis.py ends here
