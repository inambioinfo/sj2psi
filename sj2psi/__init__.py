import pandas as pd

__version__ = '0.2.2'

COLUMN_NAMES = ('chrom', 'intron_start', 'intron_stop', 'strand',
                'intron_motif', 'annotated',
                'unique_junction_reads', 'multimap_junction_reads',
                'max_overhang')


def int_to_intron_motif(n):
    if n == 0:
        return 'non-canonical'
    if n == 1:
        return 'GT/AG'
    if n == 2:
        return 'CT/AC'
    if n == 3:
        return 'GC/AG'
    if n == 4:
        return 'CT/GC'
    if n == 5:
        return 'AT/AC'
    if n == 6:
        return 'GT/AT'


def read_sj_out_tab(filename):
    """Read an SJ.out.tab file as produced by the RNA-STAR aligner into a
    pandas Dataframe

    Parameters
    ----------
    filename : str of filename or file handle
        Filename of the SJ.out.tab file you want to read in

    Returns
    -------
    sj : pandas.DataFrame
        Dataframe of splice junctions with the columns,
        ('chrom', 'intron_start', 'intron_stop', 'strand',
        'intron_motif', 'annotated', 'unique_junction_reads',
        'multimap_junction_reads', 'max_overhang')

    """
    sj = pd.read_table(filename, header=None, names=COLUMN_NAMES, sep='\s+')
    sj.intron_motif = sj.intron_motif.map(int_to_intron_motif)
    sj.annotated = sj.annotated.astype(bool)
    return sj


def chr_start_stop_to_sj_ind(chr_start_stop, sj):
    """Transform a 'chr1:100-200' string into index range of sj dataframe

    Parameters
    ----------
    chr_start_stop : str
        Genome location string of the format chr:start-stop
    sj : pandas.DataFrame
        Dataframe of splice junctions as created by read_sj_out_tab

    Returns
    -------
    ind : pandas.Series (bool)
        Boolean series which can be used to index the sj

    """
    chrom, startstop = chr_start_stop.replace(',', '').split(':')
    start, stop = map(int, startstop.split('-'))
    return (sj.chrom == chrom) & (start < sj.intron_start) \
        & (sj.intron_stop < stop)


def get_psis(sj, min_unique=5, min_multimap=10):
    """Calculate Percent spliced-in (Psi) scores of each junction

    As described in Pervouchine et al, Bioinformatics (2013)
    [doi: 10.1093/bioinformatics/bts678], we will take the approach of asking,
    how often is this donor site (5' splice site) used with this acceptor
    site (3' splice site), compared to ALL OTHER acceptors?

    Same goes for acceptor sites. How often is this acceptor site, used with
    this donor site, compared to ALL OTHER donors?

    To illustrate, check out this example. Each "-" represents 10 bp

    Splice junction fig     genome location     number of reads
    [  ]--------[    ]        chr1:100-180        90
    [  ]----------[  ]        chr1:100-200        10
    [     ]-------[  ]        chr1:130-200        40

    For the 5' splice site chr1:100, we have 90+10 = 100 total reads. Thus the
    "psi5" for chr1:100-180 is 90/100 = 0.9, and 0.1 for chr:100-200.

    For the 3' splice site chr1:200, we have 10+40 = 50 total reads. Thus the
    "psi3" for chr1:100-200 is 10/50 = 0.2, and 0.8 for chr:130-200.

    What's left is the uninteresting splice sites of chr1:180 and chr1:130,
    both of which didn't have any variance and were always used. Thus psi3
    for chr1:180 is 1.0, and psi5 for chr1:130 is 1.0 as well.

    Parameters
    ----------
    sj : pandas.DataFrame
        A splice junction dataframe as created by read_sj_out_tab, specifically
        with the columns,
        ('chrom', 'intron_start', 'intron_stop', 'strand',
        'intron_motif', 'annotated', 'unique_junction_reads',
        'multimap_junction_reads', 'max_overhang')
    min_unique : int, optional
        Minimum number of unique reads per junction. Default 5.
    min_multimap : int, optional
        Minimum number of multimapping reads per junction. Default 10

    Returns
    -------
    sj_with_psi : pandas.DataFrame
        The original dataframe, now with the columns psi5 and psi3 for
        percent spliced-in scores of each junction.

    >>> import pandas as pd
    >>> data = {'chrom': ['chr1', 'chr1', 'chr1'],
    ... 'intron_start':[100, 100, 130], 'intron_stop':[100, 200, 200],
    ... 'unique_junction_reads':[90, 10, 40],
    ... 'multimap_junction_reads':[0, 0, 0]}
    >>> sj = pd.DataFrame(data)
    >>> get_psis(sj) # doctest: +NORMALIZE_WHITESPACE
      chrom  intron_start  intron_stop  multimap_junction_reads  \\
    0  chr1              100             100                        0
    1  chr1              100             200                        0
    2  chr1              130             200                        0
    <BLANKLINE>
       unique_junction_reads  multimap_junction_reads_filtered  \\
    0                     90                                 0
    1                     10                                 0
    2                     40                                 0
    <BLANKLINE>
       unique_junction_reads_filtered  total_filtered_reads  psi5  psi3
    0                              90                    90   0.9   1.0
    1                              10                    10   0.1   0.2
    2                              40                    40   1.0   0.8
    <BLANKLINE>
    [3 rows x 10 columns]
    """
    sj['multimap_junction_reads_filtered'] = sj.multimap_junction_reads[
        sj.multimap_junction_reads >= min_multimap]
    sj['unique_junction_reads_filtered'] = sj.unique_junction_reads[
        sj.unique_junction_reads >= min_unique]
    sj['total_filtered_reads'] = sj.multimap_junction_reads_filtered.add(
        sj.unique_junction_reads_filtered)
    sj.total_filtered_reads = sj.total_filtered_reads.astype('float')

    # Calculate psi scores as in Pervouchine et al, Bioinformatics (2013)
    # doi: 10.1093/bioinformatics/bts678
    psi5_groupby = ['chrom', 'intron_start']
    psi3_groupby = ['chrom', 'intron_stop']

    groupbys = {'psi5': psi5_groupby, 'psi3': psi3_groupby}
    for name, groupby in groupbys.items():
        denominator = '{0}_denominator'.format(name)
        s = sj.groupby(groupby).total_filtered_reads.sum()
        s.name = denominator
        sj.set_index(groupby, inplace=True, drop=False)
        sj = sj.join(s)
        sj[name] = sj.total_filtered_reads / sj[denominator]
        sj.reset_index(inplace=True, drop=True)

    return sj
