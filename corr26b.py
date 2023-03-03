"""Attempt to reproduce corr26b from Li et al. 2017.

A fair amount of code is copied from sky_emissivity GitHub repo,
some of which is imported from JYJ (Yuanjie) code.
"""

import os
import time
import pvlib
import numpy as np
import pandas as pd
import datetime as dt
import matplotlib.pyplot as plt
from scipy import integrate

from main import SIGMA, get_pw, get_esky_c, li_lw, CORR26A


SITES = [
    'Bondville_IL', 'Boulder_CO', 'Desert_Rock_NV', 'Fort_Peck_MT', 
    'Goodwin_Creek_MS', 'Penn_State_PA', 'Sioux_Falls_SD']  # Tbl 1
SURF_SITE_CODES = ['BON', 'BOU', 'DRA', 'FPK', 'GWC', 'PSU', 'SXF']
LATs = [40.05, 40.13, 36.62, 48.31, 34.25, 40.72, 43.73]
LONs = [-88.37, -105.24, -116.06, -105.10, -89.87, -77.93, -96.62]
ALTs = [213, 1689, 1007, 634, 98, 376, 437]  # m
COLNAMES = [
    'yr', 'jday', 'month', 'day', 'hr', 'minute', 'dt', 'zen', 'dw_solar',
    'qc1', 'uw_solar', 'qc2', 'direct_n', 'qc3', 'diffuse', 'qc4', 'dw_ir',
    'qc5', 'dw_casetemp', 'qc6', 'dw_dometemp', 'qc7', 'uw_ir', 'qc8',
    'uw_castemp', 'qc9', 'uw_dometemp', 'qc10', 'uvb', 'qc11', 'par', 'qc12',
    'netsolar', 'qc13', 'netir', 'qc14', 'totalnet', 'qc15', 'temp', 'qc16',
    'rh', 'qc17', 'windspd', 'qc18', 'winddir', 'qc19', 'pressure', 'qc20'
]

# ASOS stations
ASOS_SITES = [
    'UNIVERSI OF WILLARD APT', 'BOULDER MUNICIPAL AIRPORT',
    'DESERT ROCK AIRPORT', 'L M CLAYTON AIRPORT', 'OXFORD UNIV',
    'UNIVERSITY PARK AIRPORT', 'JOE FOSS FIELD AIRPORT'
]
INDEX_N = [20085, 17433, 19277, 17446, 21205, 19962, 20756]
USAF = [725315, 720533, 723870, 720541, 727686, 725128, 726510]
WBAN = [94870, 160, 3160, 53806, 94017, 54739, 14944]


def pw_tdp(t_a, rh):
    # the function of calculating Pw(Pa) and Tdp(C)
    pw = 610.94 * (rh / 100) * np.exp(17.625 * (t_a - 273.15) / (t_a - 30.11))
    tdp = (243.04 * np.log(pw / 610.94)) / (17.625 - np.log(pw / 610.94))
    return pw, tdp


def int_func(x, t):
    c1 = 3.7418e8  # W um^4 / m^2 ~> 2*pi*h*c^2
    c2 = 1.4389e4  # um K         ~> hc/k_B
    out = (c1 * x ** -5) / (np.exp(c2 / (x * t)) - 1)
    return out


def get_tsky(t, ir_mea):
    # function to iteratively solve for T_sky
    l1 = 3  # um
    l2 = 50  # um
    c1 = 3.7418e8  # W um^4 / m^2 ~> 2*pi*h*c^2
    c2 = 1.4389e4  # um K         ~> hc/k_B
    y = lambda x: (c1 * np.power(x, -5)) / (np.exp(c2 / (x * t)) - 1)
    out = integrate.quad(func=y, a=l1, b=l2)
    result = out[0]  # output: result, error, infodict(?), message, ...
    delta = ir_mea - result

    delta_thresh = 0.1  # SET: within 0.1 W/m^2 of measured DLW is good enough
    if (delta > 0) & (
            np.abs(delta) > delta_thresh):  # if delta>0 guessed Tsky should increase
        t = t * 1.01
        result, t = get_tsky(t, ir_mea)
    elif (delta < 0) & (np.abs(delta) > delta_thresh):
        t = t * 0.99
        result, t = get_tsky(t, ir_mea)
    return result, t


def get_pw_esky(rh, t):
    pw = 610.94 * (rh / 100) * (np.exp(17.625 * (t - 273.15) / (t - 30.11)))
    # (22a) -- daytime clear-sky model Pw in hPa
    esky = 0.598 + 0.057 * np.sqrt(pw / 100)
    return esky, pw


def look_at_jyj():
    # Code below from python notebooks looking at 26b correlation
    filename = os.path.join("data", "jyj_2017_data", "JYJ_traindataforcollapse")
    train = pd.read_pickle(filename)
    t_a = train['temp'].values + 273.15
    rh_vals = train['rh'].values
    lw_meas = train['LWmeas'].values

    # fig, ax = plt.subplots()
    # ax.plot(train.dw_ir, train.LWmeas, ".", alpha=0.3)
    # ax.axline((1, 1), slope=1, c="0.0")
    # plt.show()

    # import test values
    filename = os.path.join("data", "jyj_2017_data", "JYJ_testdataforcollapse")
    test = pd.read_pickle(filename)
    t_a_ = test['temp'].values + 273.15
    rh_ = test['rh'].values
    pa_ = test['pressure'].values * 100
    lw_meas_ = test['LWmeas'].values

    t = 292.85
    rh = 25.1
    ir_mea = 291.8
    ir, t_sky = get_tsky(t, ir_mea)
    # ir = SIGMA * t_sky ** 4
    pw = get_pw(t, rh)
    esky = get_esky_c(pw)
    t_sky2 = esky ** (1 / 4) * t
    print(t_sky, t_sky2, t_sky - t_sky2)
    print(ir)
    return None


def process_site_yr(yr="2012"):
    # export to csv a combination of data from all SURF sites, sampled
    start_time = time.time()
    data = pd.DataFrame()  # collect all data for the given year
    for i in range(len(SITES)):
        lat = LATs[i]
        lon = LONs[i]
        alt = ALTs[i]
        folder = os.path.join(
            "/Volumes", "Lysha_drive", "Archive", "proj_data",
            "SURFRAD", SITES[i], yr
        )
        lst = os.listdir(folder)
        lst.sort()
        tmp = pd.DataFrame()
        expected_columns = len(COLNAMES)
        for f in lst:  # import data by day and concatenate to `tmp`
            filename = os.path.join(folder, f)
            try:
                df = pd.DataFrame(
                    np.loadtxt(filename, skiprows=2), columns=COLNAMES
                )
                if len(df.columns) == expected_columns:
                    df['TS'] = pd.to_datetime(
                        {'year': df.yr, 'month': df.month, 'day': df.day,
                         'hour': df.hr, 'minute': df.minute}
                    )
                    df = df.set_index('TS')
                    df = df[
                        ['zen', 'dw_solar', 'qc1', 'direct_n', 'qc3', 'diffuse',
                         'qc4', 'dw_ir', 'qc5', 'temp', 'qc16', 'rh', 'qc17',
                         'pressure', 'qc20']
                    ]
                    tmp = pd.concat([tmp, df])
                else:
                    print(
                        f"{filename} does not have expected number of columns."
                    )
            except pd.errors.ParserError as e:
                print(f"Error: {e}")

        tmp['location'] = SITES[i]
        # switch back to df
        df = tmp.copy()

        # Do some clean-up
        df = df[
            (df.qc1 == 0) & (df.qc3 == 0) &
            (df.qc4 == 0) & (df.qc5 == 0) &
            (df.qc16 == 0) & (df.qc17 == 0) &
            (df.qc20 == 0)
        ]  # REMOVE FLAGGED VALUES
        df = df[
            ['zen', 'direct_n', 'diffuse', 'dw_ir', 'dw_solar', 'temp',
             'rh', 'pressure', 'location']]  # reduce data columns
        df['temp'] = df.temp + 273.15  # convert celsius to kelvin
        # df = df[df.zen < 85]  # remove night values
        # remove negative GHI and DNI values
        df = df.loc[(df.dw_solar > 0) & (df.direct_n > 0)]

        # Reduce sample here TODO remove later(?)
        df = df.sample(frac=0.01, random_state=96)

        # apply clear sky analysis
        location = pvlib.location.Location(lat, lon, altitude=alt)
        cs_out = location.get_clearsky(df.index)
        col_rename = {
            'direct_n': 'DNI_m', 'dw_solar': 'GHI_m',
            'ghi': 'GHI_c', 'dni': 'DNI_c'
        }
        df = df.merge(cs_out, how='outer', left_index=True, right_index=True)
        df = df.rename(columns=col_rename)
        #     sdf = find_clearsky(sdf) # no clear-sky analysis for now
        data = pd.concat([data, df])  # add year of site data to `data`
        print(f"{SITES[i]} {time.time() - start_time:.3f}s")

    # After all sites have been collected
    df = data.copy()

    # Determine T_sky values, and correct for 3-50 micron range
    temp = df.temp.values
    dwir = df.dw_ir.values
    t_sky = []
    dlw = []
    for i in range(df.shape[0]):
        ir, tsky = get_tsky(temp[i], dwir[i])
        ir_act = SIGMA * tsky ** 4  # determine actual DLW using sky temp
        t_sky.append(tsky)
        dlw.append(ir_act)
    df['t_sky'] = t_sky
    df['lw_s'] = dlw
    # df['kT'] = df.GHI_m / df.GHI_c
    # kTc = df.GHI_m / df.GHI_c
    # kTc[kTc > 1] = 1
    # df['kTc'] = kTc
    df = df.rename(columns={"temp": "t_a"})

    filename = os.path.join("data", "SURFRAD", f"sites_{yr}.csv")
    df.to_csv(filename)
    return None


def asos_site_data():
    return None


if __name__ == "__main__":
    print()

    # process_site_yr(yr='2012')  # run with tsky
    # process_site_yr(yr='2013')

    filename = os.path.join("data", "SURFRAD", "sites_2012.csv")
    df = pd.read_csv(filename, index_col=0, parse_dates=True)

    # TODO import ASOS data for CF values
    # TODO write solver for MLR
    # TODO make a clear sky filter based on 10 tests

    df["pw"] = get_pw(df.t_a, df.rh) / 100  # hPa
    df["esky_c"] = get_esky_c(df.pw)
    df["lw_c"] = df.esky_c * SIGMA * np.power(df.t_a, 4)

    df = df.loc[df.zen < 85]  # remove night values
    df["cmf"] = 1 - (df.GHI_m / df.GHI_c)
    # apply 26a correlation
    # df["li_lw"] = li_lw(df.cmf, df.t_a, df.rh, c=CORR26A, lwc=df.lw_c)

    fig, ax = plt.subplots()
    ax.axline((300, 300), slope=1, ls=":", color="0.0")
    ax.scatter(df.dw_ir, df.lw_s, c=df.zen, alpha=0.2, fc=None)
    # ax.scatter(df.dw_ir, df.li_lw, c=df.zen, alpha=0.2, fc=None)
    ax.set_xlabel("Measured (uncorrected) [W/m$^{2}$]")
    ax.set_ylabel("Modeled [W/m$^{2}$]")
    # ax.set_title("Daytime (26a)")
    cbar = plt.colorbar(ax=ax)
    cbar.set_label("zenith angle")
    plt.show()

    # df["f"] = df.lw_s / df.dw_ir
    # df.f.hist(bins=100)