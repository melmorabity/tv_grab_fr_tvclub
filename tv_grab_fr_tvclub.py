#!/usr/bin/python3
# -*- coding: utf-8 -*-

# Copyright 2017 Mohamed El Morabity
#
# This program is free software: you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free Software
# Foundation, either version 3 of the License, or (at your option) any later
# version.
#
# This program is distributed in the hope that it will be useful, but WITHOUT
# ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# You should have received a copy of the GNU General Public License along with
# this program. If not, see <http://www.gnu.org/licenses/>.


"""tv_grab_fr_tvclub.py - Grab television listings for TVClub in XMLTV
format."""

import argparse
import datetime
import logging
import os
import re
import sys
import urllib
import urllib.parse
from urllib.request import Request

import lxml.etree
from lxml.etree import Element, ElementTree, XMLParser


class TVClubXMLTVGrabber:
    """Implements grabbing and processing functionalities required to generate
    XMLTV data for TVClub.
    """

    _XMLTV_URL = 'http://guide.tvclub.fr/tvguide.xml'
    _XMLTV_DATETIME_FORMAT = '%Y%m%d%H%M%S %z'

    _MAX_DAYS = 5

    _ETSI_PROGRAM_CATEGORIES = {
        'Cinéma': 'Movie / Drama',
        'Clips': 'Music / Ballet / Dance',
        'Dessin animé': 'Cartoons / Puppets',
        'Emission': '',
        'Spectacle': 'Performing arts',
        'Série': 'Movie / Drama',
        'Téléfilm': 'Movie / Drama'
    }

    # http://www.microsoft.com/typography/unicode/1252.htm
    _WINDOWS_1252_UTF_8 = {
        u"\x80": u"\u20AC",  # EURO SIGN
        u"\x82": u"\u201A",  # SINGLE LOW-9 QUOTATION MARK
        u"\x83": u"\u0192",  # LATIN SMALL LETTER F WITH HOOK
        u"\x84": u"\u201E",  # DOUBLE LOW-9 QUOTATION MARK
        u"\x85": u"\u2026",  # HORIZONTAL ELLIPSIS
        u"\x86": u"\u2020",  # DAGGER
        u"\x87": u"\u2021",  # DOUBLE DAGGER
        u"\x88": u"\u02C6",  # MODIFIER LETTER CIRCUMFLEX ACCENT
        u"\x89": u"\u2030",  # PER MILLE SIGN
        u"\x8A": u"\u0160",  # LATIN CAPITAL LETTER S WITH CARON
        u"\x8B": u"\u2039",  # SINGLE LEFT-POINTING ANGLE QUOTATION MARK
        u"\x8C": u"\u0152",  # LATIN CAPITAL LIGATURE OE
        u"\x8E": u"\u017D",  # LATIN CAPITAL LETTER Z WITH CARON
        u"\x91": u"\u2018",  # LEFT SINGLE QUOTATION MARK
        u"\x92": u"\u2019",  # RIGHT SINGLE QUOTATION MARK
        u"\x93": u"\u201C",  # LEFT DOUBLE QUOTATION MARK
        u"\x94": u"\u201D",  # RIGHT DOUBLE QUOTATION MARK
        u"\x95": u"\u2022",  # BULLET
        u"\x96": u"\u2013",  # EN DASH
        u"\x97": u"\u2014",  # EM DASH
        u"\x98": u"\u02DC",  # SMALL TILDE
        u"\x99": u"\u2122",  # TRADE MARK SIGN
        u"\x9A": u"\u0161",  # LATIN SMALL LETTER S WITH CARON
        u"\x9B": u"\u203A",  # SINGLE RIGHT-POINTING ANGLE QUOTATION MARK
        u"\x9C": u"\u0153",  # LATIN SMALL LIGATURE OE
        u"\x9E": u"\u017E",  # LATIN SMALL LETTER Z WITH CARON
        u"\x9F": u"\u0178",  # LATIN CAPITAL LETTER Y WITH DIAERESIS
    }

    def __init__(self, generator=None, generator_url=None, logger=None):
        self._logger = logger or logging.getLogger(__name__)

        self._xmltv = self._get_programs()
        self._channels = self._retrieve_available_channels()
        self._generator = generator
        self._generator_url = generator_url

    def _get_programs(self):
        """Get TVClub programs in XMLTV format as a XML Element object."""

        self._logger.debug('Getting TVClub programs')

        self._logger.debug('Retrieveing URL %s', self._XMLTV_URL)
        request = Request(self._XMLTV_URL)
        with urllib.request.urlopen(request) as response:
            return lxml.etree.fromstring(
                response.read(),
                parser=XMLParser(remove_blank_text=True)
            )

    def _retrieve_available_channels(self):
        """Retrieve all available channels, identified by their XMLTV ID, from
        TVClub.
        """

        self._logger.debug('Getting available channels')

        channels = {}
        for channel in self._xmltv.iter(tag='channel'):
            xmltv_id = channel.get('id')
            display_name = channel.findtext('display-name')
            if xmltv_id is not None and display_name is not None:
                channels[xmltv_id] = {'display_name': display_name}

        return channels

    def get_available_channels(self):
        """Return the list of all available channels from TVClub, as a
        dictionary.
        """

        return self._channels

    def _etsi_category(self, category):
        """Translate TVClub program category to ETSI EN 300 468 category."""

        etsi_category = self._ETSI_PROGRAM_CATEGORIES.get(category)
        if etsi_category is None:
            self._logger.warning(
                'TVClub category %s has no defined ETSI equivalent', category
            )

        return etsi_category

    def _fix_windows_1252(self, text):
        """Replace in a string all Windows-1252 specific chars to UTF-8."""

        return ''.join([self._WINDOWS_1252_UTF_8.get(c, c) for c in text])

    def _update_program_xmltv(self, program_xml):
        """Fix a TVClub program XML Element to comply the XMLTV standard."""

        # Although TVClub programs are supposed to be encoded in UTF-8, some
        # texts may be encoded in Windows-1252

        for text in 'title', 'sub-title', 'desc':
            xml = program_xml.find(text)
            if xml is not None:
                xml.text = self._fix_windows_1252(xml.text).strip()
                if text == 'sub-title':
                    xml.set('lang', 'fr')

        # Description
        desc_xml = program_xml.find('desc')
        if desc_xml is not None:
            desc = self._fix_windows_1252(desc_xml.text).strip()
            desc_xml.text = desc
            desc_xml.set('lang', 'fr')

        # Categories
        category_xml = program_xml.find('category')
        if category_xml is not None:
            category = category_xml.text.strip()
            if category != '':
                etsi_category = self._etsi_category(category)
                if etsi_category is not None and etsi_category != '':
                    etsi_category_xml = Element('category')
                    etsi_category_xml.text = etsi_category
                    index = category_xml.getparent().index(category_xml)
                    program_xml.insert(index, etsi_category_xml)

    @staticmethod
    def _get_program_id(program_xml):
        """Generate a unique ID for a XMLTV program, based on its channel, its
        start and stop times, and its title.
        """

        return '{}|{}|{}|{}'.format(program_xml.get('channel', ''),
                                    program_xml.get('start', ''),
                                    program_xml.get('stop', ''),
                                    program_xml.findtext('title', ''))

    def _get_xmltv_data(self, xmltv_ids, days=1, offset=0,
                        channels_only=False):
        """Get TVClub program data in XMLTV format as XML ElementTree
        object.
        """

        if days + offset > self._MAX_DAYS:
            self._logger.warning(
                'Grabber can only fetch programs up to %i days in the future.',
                self._MAX_DAYS
            )
            days = min(self._MAX_DAYS - offset, self._MAX_DAYS)

        root_xml = Element(
            'tv',
            attrib={
                'source-info-name': 'TVClub',
                'source-info-url': 'http://forum.tvclub.fr/programmes-epg/'
                                   'index.php',
                'source-data-url': self._XMLTV_URL
            }
        )
        if self._generator is not None:
            root_xml.set('generator-info-name', self._generator)
        if self._generator_url is not None:
            root_xml.set('generator-info-url', self._generator_url)

        for channel_xml in self._xmltv.iter(tag='channel'):
            # Only keep channels for selected XMLTV IDs
            if channel_xml.get('id') in xmltv_ids:
                root_xml.append(channel_xml)

        if not channels_only:
            program_ids = []
            first_day = datetime.date.today() + datetime.timedelta(days=offset)
            last_day = (datetime.date.today() +
                        datetime.timedelta(days=days + offset - 1))
            for program_xml in self._xmltv.iter(tag='programme'):
                # TVClub data contain programs starting between 5:00 AM and
                # 4:59 AM 4 days later. Ignore programs outside the fetch
                # range.
                stop = datetime.datetime.strptime(
                    program_xml.get('stop'),
                    self._XMLTV_DATETIME_FORMAT
                ).date()
                start = datetime.datetime.strptime(
                    program_xml.get('start'),
                    self._XMLTV_DATETIME_FORMAT
                ).date()
                if stop < first_day or start > last_day:
                    continue

                # Ignore duplicate programs
                program_id = self._get_program_id(program_xml)
                if program_id in program_ids:
                    continue
                program_ids.append(program_id)

                self._update_program_xmltv(program_xml)
                root_xml.append(program_xml)

        return ElementTree(root_xml)

    def write_xmltv(self, xmltv_ids, output_file, days=1, offset=0,
                    channels_only=False):
        """Grab TVClub programs in XMLTV format and write them to file."""

        self._logger.debug('Writing XMLTV program to file %s', output_file)

        xmltv_data = self._get_xmltv_data(xmltv_ids, days, offset,
                                          channels_only)
        xmltv_data.write(output_file, encoding='UTF-8', xml_declaration=True,
                         pretty_print=True)


_PROGRAM = 'tv_grab_fr_tvclub'
__version__ = '1.0'
__url__ = 'https://github.com/melmorabity/tv_grab_fr_tvclub'

_DESCRIPTION = 'France (TVClub)'
_CAPABILITIES = ['baseline', 'manualconfig']

_DEFAULT_DAYS = 1
_DEFAULT_OFFSET = 0

_DEFAULT_CONFIG_FILE = os.path.join(os.environ['HOME'], '.xmltv',
                                    _PROGRAM + '.conf')

_DEFAULT_OUTPUT = '/dev/stdout'


def _print_description():
    """Print the description for the grabber."""

    print(_DESCRIPTION)


def _print_version():
    """Print the grabber version."""

    print('This is {} version {}'.format(_PROGRAM, __version__))


def _print_capabilities():
    """Print the capabilities for the grabber."""

    print('\n'.join(_CAPABILITIES))


def _parse_cli_args():
    """Command line argument processing."""

    parser = argparse.ArgumentParser(
        description='get television listings for TVClub in XMLTV format'
    )
    parser.add_argument('--description', action='store_true',
                        help='print the description for this grabber')
    parser.add_argument('--version', action='store_true',
                        help='show the version of this grabber')
    parser.add_argument('--capabilities', action='store_true',
                        help='show the capabilities this grabber supports')
    parser.add_argument(
        '--configure', action='store_true',
        help='generate the configuration file by asking the users which '
             'channels to grab'
    )
    parser.add_argument(
        '--days', type=int, default=_DEFAULT_DAYS,
        help='grab DAYS days of TV data (default: %(default)s)'
    )
    parser.add_argument(
        '--offset', type=int, default=_DEFAULT_OFFSET,
        help='grab TV data starting at OFFSET days in the future (default: '
             '%(default)s)'
    )
    parser.add_argument(
        '--output', default=_DEFAULT_OUTPUT,
        help='write the XML data to OUTPUT instead of the standard output'
    )
    parser.add_argument(
        '--config-file', default=_DEFAULT_CONFIG_FILE,
        help='file name to write/load the configuration to/from (default: '
             '%(default)s)'
    )
    parser.add_argument(
        '--list-channels', action='store_true',
        help='output a list of all channels that data is available for (in '
             'xmltv format)'
    )

    log_level_group = parser.add_mutually_exclusive_group()
    log_level_group.add_argument('--quiet', action='store_true',
                                 help='only print error-messages on STDERR')
    log_level_group.add_argument(
        '--debug', action='store_true',
        help='provide more information on progress to stderr to help in '
             'debugging'
    )

    return parser.parse_args()


def _read_configuration(config_file=_DEFAULT_CONFIG_FILE):
    """Load channel XMLTV IDs from the configuration file."""

    xmltv_ids = []
    with open(config_file, 'r') as config:
        for line in config:
            match = re.search(r'^\s*channel\s*=\s*(.+)\s*$', line)
            if match is not None:
                xmltv_ids.append(match.group(1))

    return xmltv_ids


def _write_configuration(xmltv_ids, config_file=_DEFAULT_CONFIG_FILE):
    """Write specified channels to the specified configuration file."""

    config_dir = os.path.dirname(os.path.abspath(config_file))
    if not os.path.exists(config_dir):
        os.mkdir(config_dir)

    with open(config_file, 'w') as config:
        for xmltv_id in xmltv_ids:
            print('channel={}'.format(xmltv_id), file=config)


def _configure(available_channels, config_file=_DEFAULT_CONFIG_FILE):
    """Prompt channels to configure and write them into the configuration
    file.
    """

    xmltv_ids = []
    answers = ['yes', 'no', 'all', 'none']
    select_all = False
    select_none = False
    print('Select the channels that you want to receive data for.',
          file=sys.stderr)
    for xmltv_id in available_channels:
        display_name = available_channels[xmltv_id]['display_name']
        if not select_all and not select_none:
            while True:
                prompt = '{} [{} (default=no)] '.format(display_name,
                                                        ','.join(answers))
                answer = input(prompt).strip()
                if answer in answers or answer == '':
                    break
                print(
                    'invalid response, please choose one of {}'.format(
                        ','.join(answers)
                    ),
                    file=sys.stderr
                )
            select_all = answer == 'all'
            select_none = answer == 'none'
        if select_all or answer == 'yes':
            xmltv_ids.append(xmltv_id)
        if select_all:
            print('{} yes'.format(display_name), file=sys.stderr)
        elif select_none:
            print('{} no'.format(display_name), file=sys.stderr)

    _write_configuration(xmltv_ids, config_file)


def _main():
    """Main execution path."""

    logger = logging.getLogger(__name__)
    logger.addHandler(logging.StreamHandler())

    args = _parse_cli_args()

    if args.version:
        _print_version()
        sys.exit()

    if args.description:
        _print_description()
        sys.exit()

    if args.capabilities:
        _print_capabilities()
        sys.exit()

    if args.debug:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR
    else:
        log_level = logging.INFO

    logger.setLevel(log_level)

    tvclub = TVClubXMLTVGrabber(generator=_PROGRAM, generator_url=__url__,
                                logger=logger)
    available_channels = tvclub.get_available_channels()

    logger.info('Using configuration file %s', args.config_file)

    if args.configure:
        _configure(available_channels, args.config_file)
        sys.exit()

    if not os.path.isfile(args.config_file):
        logger.error(
            'You need to configure the grabber by running it with --configure'
        )
        sys.exit(1)

    xmltv_ids = _read_configuration(args.config_file)
    if not xmltv_ids:
        logger.error(
            'Configuration file %s is empty, delete and run with --configure',
            args.config_file
        )

    tvclub.write_xmltv(xmltv_ids, args.output, days=args.days,
                       offset=args.offset, channels_only=args.list_channels)

if __name__ == '__main__':
    _main()
