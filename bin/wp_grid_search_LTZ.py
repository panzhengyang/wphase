#!/usr/bin/python
# *-* coding: iso-8859-1 *-*

######################################
# GRID SEARCH FOR WPHASE INVERSION
###
# Z.Duputel, L.Rivera and H.Kanamori
#  2009/07/15 -- initial version for grid search
#  2009/07/19 -- optimization for time shift : B-tree sampling method
#  2009/07/26 -- optimization for centroïd position : Oct-tree sampling method
#  2009/09/09 -- plot routines are now in a separate script
#  2010/01/08 -- allow the possibility to extend the spatial GS area 
#                (if optimums are on edge)
import os,re,shutil,sys,time,getopt
from EQ import *

WPHOME = os.path.expandvars('$WPHASE_HOME')
if WPHOME[-1] != '/':
	WPHOME += '/'

BIN = WPHOME+'bin/'


REPREPARE_TS = BIN+'reprepare_wp_ts_LTZ.csh'
WPINV_TS     = BIN+'wpinversion_LTZ -imas ts_i_master -ifil o_wpinversion -ofil ts_o_wpinversion -ocmtf ts_WCMTSOLUTION '+\
                   '-ps ts_p_wpinversion -wpbm ts_wpinv.pgm -log LOG/_ts_wpinversion.log -osyndir ts_SYNTH -pdata ts_fort.15'

RECALCSYN_XY = BIN+'recalc_fast_synths_LTZ.csh'
REPREPARE_XY = BIN+'reprepare_wp_xy_LTZ.csh'
WPINV_XY     = BIN+'wpinversion_LTZ -imas xy_i_master -ifil xy_o_wpinversion -ofil xy_o_wpinversion '+\
                   '-ps xy_p_wpinversion -wpbm xy_wpinv.pgm -log LOG/_xy_wpinversion.log -osyndir xy_SYNTH -pdata xy_fort.15'

WPINV_DP     = BIN+'wpinversion_LTZ -imas dp_i_master -ifil dp_o_wpinversion -ofil dp_o_wpinversion '+\
                   '-wpbm dp_wpinv.pgm -log LOG/_dp_wpinversion.log -osyndir dp_SYNTH -pdata dp_fort.15'


def grep(chaine, file):
	out = [];
	rms = re.compile(chaine)
	ps  = open(file, 'r')
	for line in ps:
		if rms.match(line):
			out.append(line)
	ps.close()
	return(out)

def grep2(list, file):
	out   = [];
	ps    = open(file, 'r')
	lines = ps.readlines()
	ps.close()
	for chaine in list:
		rexp = re.compile(chaine)
		for line in lines:
			if rexp.match(line):
				out.append(line)
				break
	return(out)

def addrefsol(cmtref,cmtfile):
	cmtf = open(cmtref,'r')
	L=cmtf.readlines()
	cmtf.close()
	cmtf = open(cmtfile,'a')
	if len(L) < 13:
		print '*** ERROR (reading reference solution) ***' 
		print 'incomplete cmtfile: %s'%(cmtref)
		sys.exit(1)
	for l in L[7:]:
		cmtf.write(l)
	cmtf.close()

def find_coor(coor,lat,lon):
	for cds in coor:
		if int(0.5+lat*100.) == int(0.5+cds[0]*100.) \
		       and int(0.5+lon*100.) == int(0.5+cds[1]*100.):
			return 1
	return 0

def add_coor(coor,lat,lon,prevcoor=[]):
	crds = []
	crds.extend(coor)
	crds.extend(prevcoor)
	if find_coor(crds,lat,lon):
		return 1
	coor.append([lat,lon])
	return 0

def search_emptyedges(emptyedges,lat,lon,dx,prevcoor=[]):
	crds = [[lat+dx,lon-dx],[lat+dx,lon   ],[lat+dx,lon+dx],[lat   ,lon+dx],\
		[lat-dx,lon+dx],[lat-dx,lon   ],[lat-dx,lon-dx],[lat   ,lon-dx]]
	for crd in crds:
		add_coor(emptyedges,crd[0],crd[1],prevcoor)

def rm(fd):
	if os.path.islink(fd) or os.path.isfile(fd):
		os.remove(fd)
	else:
		shutil.rmtree(fd)

def addslash(direc):
	if len(direc) > 0:
		if direc[-1] != '/':
			direc += '/'
	return direc

def copy_GF(idir,odir,include=r'.*\.SAC$',exclude=r'.*sac.*'):
	if not os.path.exists(odir):
		os.mkdir(odir)
	idir = addslash(idir)
	odir = addslash(odir)
	b    = len(idir)
	I    = re.compile(include)
	E    = re.compile(exclude)
	for li in os.walk(idir):
		ipath = addslash(li[0])
		opath = addslash(odir+li[0][b:])
		for d in li[1]:
			os.mkdir(opath+d)
		for f in li[2]:
			if E.match(f) and not I.match(f):
				continue
			else:
				shutil.copy(ipath+f,opath)

def grid_search_xy(datdir,cmtref,ftable,eq,wpwin=[15.],flagref=0,dmin=0.,dmax=90.,fileout='stdout'):
	if fileout == 'stdout':
		fid = sys.stdout
		flag = 0
	else:
		fid = open(fileout,'w')
		flag = 1
	fid.write('CENTROID POSITION GRID SEARCH\n')

	# Initialize variables #################
	o_file = 'grid_search_xy_out'
	format    = '%03d %03d %8.2f %8.2f %8.2f %8.2f %8.2f %12.7f %12.7f\n'
	tmpfile = '_tmp_xy_table'

	Nit  = 2
	dx   = 0.4
	lat1 = eq.lat - 1.2
	lat2 = eq.lat + 1.2
	lon1 = eq.lon - 1.2
	lon2 = eq.lon + 1.2 

	ts = eq.ts
	hd = eq.hd
	
	lat = lat1
	coor = []
	while int(100*lat) <= int(100*lat2):
		lon = lon1
		while int(100*lon) <= int(100*lon2):
			coor.append([lat,lon])
			lon += dx
		lat += dx

	Nopt   = [5,5,4,3]
	rmsopt = []
	latopt = []
	lonopt = []
	for i in xrange(max(Nopt)):
		rmsopt.append(1.e10)
		latopt.append(lat2)
		lonopt.append(lon1)

	# Setting files and directories ########
	cmttmp = cmtref+'_xy_tmp'
	if os.access(o_file,os.F_OK):
		rm(o_file)
	shutil.copy('o_wpinversion','xy_o_wpinversion')
	eq.wimaster(datdir,ftable,cmttmp,'xy_i_master',dmin,dmax,'./xy_GF/',wpwin) 	
	if os.access('xy_SYNTH',os.F_OK):
		rm('xy_SYNTH')
	if os.access('xy_DATA',os.F_OK):
		rm('xy_DATA')
	if os.access('xy_WCMTs',os.F_OK):
		rm('xy_WCMTs')
	os.mkdir('xy_WCMTs')
	os.mkdir('xy_SYNTH')
	os.mkdir('xy_DATA')


	# (re)Compute initial solution #########
	eq_gs = EarthQuake()
 	EQcopy(eq_gs,eq)
	eq_gs.wcmtfile(cmttmp,ts,hd)
	os.system(RECALCSYN_XY+' > LOG/_log_py_recalsyn_xy')
	os.system(REPREPARE_XY+'> LOG/_log_py_reprepare_xy')
	os.system(WPINV_XY+' -ocmtf xy_WCMTs/xy_WCMTSOLUTION_ini -noref > LOG/_log_py_wpinv_xy')
	out  = grep(r'^W_cmt_err:', 'LOG/_xy_wpinversion.log')
	rmsini    = float(out[0].strip('\n').split()[1])
	nrmsini   = float(out[0].strip('\n').split()[2])
	rmsopt[0] = rmsini # a priori optimum solution == initial (pde) solution
	latopt[0] = eq.lat
	lonopt[0] = eq.lon

	# Grid search ##########################
	it    = 0
	ncel  = 0
	Nexp  = 0
	prevcoor  = []
	tmp_table = open(tmpfile, 'w') 
	while (it < Nit):
		if Nexp == 0:
			fid.write('Iteration %d:\n' % (it+1))
			if it != 0:
				dx = dx/2.
				coor = []
				for i in xrange(Nopt[it]):
					add_coor(coor,latopt[i]+dx,lonopt[i]-dx,prevcoor)
					add_coor(coor,latopt[i]+dx,lonopt[i]   ,prevcoor)
					add_coor(coor,latopt[i]+dx,lonopt[i]+dx,prevcoor)
					add_coor(coor,latopt[i]   ,lonopt[i]+dx,prevcoor)
					add_coor(coor,latopt[i]-dx,lonopt[i]+dx,prevcoor)
					add_coor(coor,latopt[i]-dx,lonopt[i]   ,prevcoor)
					add_coor(coor,latopt[i]-dx,lonopt[i]-dx,prevcoor)
					add_coor(coor,latopt[i]   ,lonopt[i]-dx,prevcoor)
		prevcoor.extend(coor)
 		for cds in coor:
 			eq_gs.lat, eq_gs.lon = cds[0], cds[1]
 			eq_gs.wcmtfile(cmttmp,ts,hd)
			os.system(RECALCSYN_XY+' > LOG/_log_py_recalsyn_xy')
			os.system(REPREPARE_XY+' > LOG/_log_py_reprepare_xy')
			os.system(WPINV_XY+' -ocmtf xy_WCMTs/xy_WCMTSOLUTION_%03d -noref > LOG/_log_py_wpinv_xy'%ncel)
			out  = grep(r'^W_cmt_err:', 'LOG/_xy_wpinversion.log')
			rms  = float(out[0].strip('\n').split()[1])
			nrms = float(out[0].strip('\n').split()[2])
			fid.write('   cell %3d : lat=%8.3fdeg lon=%8.3fdeg, rms = %12.7f mm\n'% (ncel+1,eq_gs.lat,eq_gs.lon,rms))
			for i in xrange(Nopt[it]):
				if rms < rmsopt[i]:
					for j in xrange(Nopt[it]-1,i-1,-1):
						rmsopt[j] = rmsopt[j-1]
						latopt[j] = latopt[j-1]
						lonopt[j] = lonopt[j-1]
					rmsopt[i] = rms
					latopt[i] = eq_gs.lat
					lonopt[i] = eq_gs.lon
					break
			tmp_table.write(format%(ncel,it,ts,hd,eq_gs.lat,eq_gs.lon,eq_gs.dep,rms,nrms))
			tmp_table.flush()
			ncel += 1
		fid.write('Optimum centroid location: %8.3f %8.3f;  rms = %12.7f mm\n'%(latopt[0], lonopt[0], rmsopt[0]))
		# Spatial grid-search extension
		if (Nexp < 5):
			coor = []
			search_emptyedges(coor,eq.lat,eq.lon,dx,prevcoor)
			for j in xrange(Nopt[it]):
				search_emptyedges(coor,latopt[j],lonopt[j],dx,prevcoor)
			if len(coor):
				print ' ... extending the spatial grid-search area ... '
				if it == 0:
					lons = []
					lats = []
					for lat,lon in coor:
						if lon < lon1 or lon > lon2:
							if not lons.count(lon):
								lons.append(lon)
						if lat < lat1 or lat > lat1:
							if not lats.count(lat):
								lats.append(lat)
					if len(lats):
						minlat,maxlat = min(lats),max(lats)
						if minlat < lat1:
							lat1 = minlat
						if maxlat > lat2:
							lat2 = maxlat
						for clat in lats:
							lon = lon1
							while lon <= lon2:
								add_coor(coor,clat,lon,prevcoor)
								lon += dx						
					if len(lons):
						minlon,maxlon = min(lons),max(lons)
						if minlon < lon1:
							lon1 = minlon
						if maxlon > lon1:
							lon2 = maxlon
						for clon in lons:
							lat = lat1
							while lat <= lat2:
								add_coor(coor,lat,clon,prevcoor)
								lat += dx
					Nexp += 1
					continue
				else:
					Nexp += 1
					continue
			prevcoor.extend(coor)
		Nexp = 0
		it += 1
	tmp_table.close()
	tmp_table = open(tmpfile, 'r')
	out_table = open(o_file, 'w')
	out_table.write('%8.3f %8.3f %12.7f\n'%(latopt[0], lonopt[0], rmsopt[0]))
	out_table.write('%8.3f %8.3f %12.7f\n'%(   eq.lat,    eq.lon, rmsini))	
       	out_table.write(tmp_table.read())
       	out_table.close()
       	tmp_table.close()
	rm(tmpfile)

	eq_gs.lat,eq_gs.lon = latopt[0],lonopt[0]
	eq_gs.wcmtfile(cmttmp,ts,hd)
	os.system(RECALCSYN_XY+'> LOG/_log_py_recalsyn_xy')
	os.system(REPREPARE_XY+'> LOG/_log_py_reprepare_xy')
	if flagref:
		addrefsol(cmtref,cmttmp)
		fr = " "
	else:
		fr = "-noref"
	if flag:
		fid.close()
		os.system(WPINV_XY+' -ocmtf xy_WCMTSOLUTION %s >> '%fr+fileout)
	else:
		os.system(WPINV_XY+' -ocmtf xy_WCMTSOLUTION %s'%fr)
	
	shutil.copy('xy_WCMTSOLUTION','xy_WCMTs')	

	# Set Mww
	out  = grep(r'^Wmag:', 'LOG/_xy_wpinversion.log')
	eq.mag = float(out[0].split()[1]) ;
	eq.lat = latopt[0]
	eq.lon = lonopt[0]


def grid_search_ts(datdir,cmtref,ftable,eq,wpwin=[15.],flagref=0,dmin=0.,dmax=90.,fileout='stdout'):
	if fileout == 'stdout':
		fid = sys.stdout
		flag = 0
	else:
		fid = open(fileout,'w')
		flag = 1
	fid.write('CENTROID TIME DELAY GRID SEARCH\n')
	
	# Initialize variables #################
	o_file  = 'grid_search_ts_out'
	tmpfile = '_tmp_ts_table'
	Nit = 3
	Sts = [4.,4.,2.,1.]

	tsini = eq.ts
	hdini = eq.hd
	
	if eq.mag < 5.5:
	 	ts1 = 1.
		ts2 = tsini*3.	
		if ts2 > 60.:
			ts2 = 60.	
	else:
		ts1 =  1. 
		if eq.mag <= 7.0:
			ts2 = 30. 
		elif eq.mag <8.0:
			ts2 = 48. 
		elif eq.mag < 8.5: 		
			ts2 = 56. 
		else: 
			ts2 = 168. 
	########################################


	cmttmp = cmtref+'_ts_tmp'
	eq.wimaster(datdir,ftable,cmttmp,'ts_i_master',dmin,dmax,'ts_GF',wpwin)
	
	if os.access('ts_SYNTH',os.F_OK):
		rm('ts_SYNTH')
	os.mkdir('ts_SYNTH')
	if os.path.exists('ts_GF'):
		rm('ts_GF')
	copy_GF('GF','ts_GF')
	if os.access(o_file,os.F_OK):
		rm(o_file)
	
	# Grid search
	out     = grep(r'^W_cmt_err:', 'LOG/wpinversion.log')			
	rmsini  = float(out[0].strip('\n').split()[1])
	nrmsini = float(out[0].strip('\n').split()[2])

	its = 0
	tsopt   = tsini
	rmsopt  = rmsini
	tsopt2  = ts1
	rmsopt2 = 1.1e10
	tmp_table = open(tmpfile, 'w')
	format    = '%02d %8.2f %8.2f %8.2f %8.2f %12.8f %12.8f\n'
	for j in xrange(Nit):
		sts = Sts[j]
		if j>0:
			if (tsopt2 <= tsopt):
				ts1 = tsopt2 - sts/2.
				ts2 = tsopt  + sts/2.
			elif(tsopt2 > tsopt):
				ts1 = tsopt  - sts/2.
				ts2 = tsopt2 + sts/2.
			if ts1 < 1.:
				ts1 += 2.
		fid.write('iteration %d (%f<=ts<=%f)\n'% (j+1,ts1,ts2))
		ts = ts1
		while ts < ts2+sts:
			eq.wcmtfile(cmttmp,ts,ts)
			os.system(REPREPARE_TS+' > LOG/_log_py_reprepare_ts')
			os.system(WPINV_TS+' -noref > LOG/_log_py_wpinv_ts')
			out  = grep(r'^W_cmt_err:', 'LOG/_ts_wpinversion.log')			
			rms  = float(out[0].strip('\n').split()[1])
			nrms = float(out[0].strip('\n').split()[2])
			tmp_table.write(format%(its, ts, eq.lat, eq.lon, eq.dep, rms, nrms))
			tmp_table.flush()
			if rms < rmsopt:
				tsopt2  = tsopt
				rmsopt2 = rmsopt
				tsopt   = ts
				rmsopt  = rms
			elif rms < rmsopt2:
				tsopt2  = ts
				rmsopt2 = rms
			fid.write('   ts=hd = %4.1f sec, rms = %12.7f mm\n'% (ts,rms))
			its += 1
			ts += sts
		fid.write('   after iteration %d : tsopt=%4.1f sec rms =%12.7f mm\n'%(j+1,tsopt, rmsopt))
	fid.write('\nFinal Optimum values: time_shift (=half_duration) =  %5.1f   rms = %12.7f mm\n'%(tsopt, rmsopt))		
	tmp_table.close()

	tmp_table = open(tmpfile,'r')
	out_table = open(o_file,'w')
	out_table.write('%5.1f%12.7f\n'%(tsopt, rmsopt))	
	out_table.write('%5.1f%12.7f\n'%( tsini, rmsini))
	out_table.write(tmp_table.read())
	out_table.close()
	tmp_table.close()
	rm(tmpfile)
	
	eq.wcmtfile(cmttmp,tsopt,tsopt)
	if flagref:
		addrefsol(cmtref,cmttmp)
		fr = " "
	else:
		fr = "-noref"
	os.system(REPREPARE_TS)
	if flag:
		fid.close()	
		os.system(WPINV_TS+' %s >> '%fr)
	else:
		os.system(WPINV_TS+' %s'%fr)

	# Set Mww
	out  = grep(r'^Wmag:', 'LOG/_ts_wpinversion.log')
	eq.mag = float(out[0].split()[1]) ;

	return [tsopt,tsopt]

def fast_grid_search_ts(datdir,cmtref,ftable,eq,wpwin=[15.],flagref=0,dmin=0.,dmax=90.,fileout='stdout'):
	if fileout == 'stdout':
		fid  = sys.stdout
		flag = 0
	else:
		fid = open(fileout,'w')
		flag = 1
	fid.write('FAST CENTROID TIME DELAY GRID SEARCH\n')		

	# Initialize variables #################
	o_file = 'grid_search_ts_out'

	Nit = 3
	sts = 4.

	tsini = eq.ts
	hdini = eq.hd
	
	if eq.mag < 5.5:
	 	ts1 = 1.
		ts2 = tsini*3.	
		if ts2 > 60.:
			ts2 = 60.	
	else:
		ts1 =  1. 
		if eq.mag <= 7.0:
			ts2 = 30. 
		elif eq.mag < 8.5: 		
			ts2 = 56. 
		else: 
			ts2 = 168. 
	#######################################
	
	cmttmp = cmtref+'_ts_tmp'
	eq.wcmtfile(cmttmp,tsini,hdini)
	eq.wimaster(datdir,ftable,cmttmp,'ts_i_master',dmin ,dmax,'ts_GF',wpwin)
	if os.access('ts_SYNTH',os.F_OK):
		rm('ts_SYNTH')
	os.mkdir('ts_SYNTH')
	if os.access('ts_GF',os.F_OK):
		rm('ts_GF')
	os.symlink('./GF','ts_GF')
	if os.access(o_file,os.F_OK):
		rm(o_file)
	# Grid search
	fid.write('  ts1 = %5.1f sec, step = %5.1f sec, ts2 = %5.1f sec \n'%(ts1,sts,ts2))  	
	format  = '%02d %8.2f %8.2f %8.2f %8.2f %12.8f %12.8f\n'
 	#print WPINV_TS+' -noref -ts %4.1f %4.1f %4.1f -Nit 3 -ogsf %s -ifil o_wpinversion'% (ts1,sts,ts2,o_file)
	if flag:
		fid.close()
		os.system(WPINV_TS+' -noref -ts %4.1f %4.1f %4.1f -Nit 3 -ogsf %s -ifil o_wpinversion >> %s'% (ts1,sts,ts2,o_file,fileout))
	else:
		os.system(WPINV_TS+' -noref -ts %4.1f %4.1f %4.1f -Nit 3 -ogsf %s -ifil o_wpinversion'% (ts1,sts,ts2,o_file))
	

	# Recompute optimum solution
	tmp_table = open(o_file, 'r')
	tsopt, rmsopt = map(float,tmp_table.readline().strip('\n').split())
 	tmp_table.close()
	rm('ts_GF')
	copy_GF('GF','ts_GF')
 	eq.wcmtfile(cmttmp,tsopt,tsopt)
	if flagref:
		addrefsol(cmtref,cmttmp)
		fr = " "
	else:
		fr = "-noref"
 	os.system(REPREPARE_TS)
	if flag:
		os.system(WPINV_TS+' %s >> '%fr+fileout)
	else:
		os.system(WPINV_TS+' %s'%fr)

	# Set Mww
	out  = grep(r'^Wmag:', 'LOG/_ts_wpinversion.log')
	eq.mag = float(out[0].split()[1]) ;
	
	return [tsopt,tsopt]



def usage():
	print 'usage: wp_grid_search [-s] [-t] [-p] [-i] ... [--help]'

def disphelp():
	print 'Centroid time-shift and centroid position grid search\n'
	usage()
	print '\nAll parameters are optional:'
	print '   -s, --slow           use a  time grid-search considering ts=fd'
	print '   -t, --onlyts         centroid time-shift grid search only'
	print '   -p, --onlyxy         centroid position grid search only'
	print '   -i, --imas \'file\'    set i_master file (i_master)'
	print '   -n, --noref          do not use the reference solution in cmtfile (ref. sol. used)'
	print '\n   -h, --help           display this help and exit'
	print '\nReport bugs to: <zacharie.duputel@eost.u-strasbg.fr>'

##### MAIN #####	
if __name__ == "__main__":
	try:
		opts, args = getopt.gnu_getopt(sys.argv[1:],'stpdi:nh',["slow","onlyts","onlyxy","enabdp","imas=","noref","help"])
	except getopt.GetoptError, err:
		print '*** ERROR ***'
		print str(err)
		usage()
		sys.exit(1)
	
	i_master = 'i_master' 
	fastflag = 1	
	flagts   = 1
	flagxy   = 1
	flagref  = 1
	for o, a in opts:
		if o == '-h' or o == '--help':
			disphelp()
			sys.exit(0)
		if o == '-s' or o == '--slow':
			fastflag = 0
		if o == '-t' or o == '--onlyts':
			if flagts == 0:
				print '** ERROR (options -t and -p cannot be used simultaneously) **'
				usage()
				sys.exit(1)
			flagxy = 0
			flagts = 1
		if o == '-p' or o == '--onlyxy':
			if flagxy == 0:
				print '** ERROR (options -t and -p cannot be used simultaneously) **'
				usage()
				sys.exit(1)
			flagts = 0
			flagxy = 1
		if o == '-i' or o == '--imas':
			i_master = a
		if o == '-n' or o == '--noref':
			flagref = 0
			
	out    = grep2([r'^SEED',r'^CMTFILE',r'^EVNAME',r'^filt_cf1',r'^filt_cf2',\
				 r'^WP_WIN'], i_master)
 	dat    = out[0].replace(':','').strip('\n').split()[1]
 	cmtref = out[1].replace(':','').strip('\n').split()[1]
	evname = out[2].split(':')[1].strip().replace(' ','_').replace(',','')
	wpwin  = map(float,out[5].replace(':','').strip('\n').split()[1:])
	ftable = []
 	ftable.append(float(out[3].replace(':','').strip('\n').split()[1]))
 	ftable.append(float(out[4].replace(':','').strip('\n').split()[1]))
	
	try:
		out    = grep(r'^DMIN', i_master)
		dmin   = float(out[0].replace(':','').strip('\n').split()[1])
	except:
		dmin   = 0.
	try:
		out    = grep(r'^DMAX', i_master)
		dmax   = float(out[0].replace(':','').strip('\n').split()[1])
	except:
		dmax   = 90.
		
 	eq   = EarthQuake()
 	eq.rcmtfile(cmtref)
	eq.title = evname.strip().replace(' ','_').replace(',','')
	cmtf = open(cmtref,'r')
	L=cmtf.readlines()
	cmtf.close()
	if len(L) < 13:
		print '*** WARNING : no reference solution in %s'%(cmtref)
		flagref = 0
	
 	if flagts == 1:
 		if fastflag == 1:
 			[eq.ts,eq.hd]=fast_grid_search_ts(dat,cmtref,ftable,eq,wpwin,flagref,dmin,dmax)
 		else:
 			[eq.ts,eq.hd]=grid_search_ts(dat,cmtref,ftable,eq,wpwin,flagref,dmin,dmax)
	if flagxy == 1:
		grid_search_xy(dat,cmtref,ftable,eq,wpwin,flagref,dmin,dmax)
	