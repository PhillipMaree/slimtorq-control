# FIXME: before you push into master...
RUNTIMEDIR=/usr/bin/../include/omc/c/
#COPY_RUNTIMEFILES=$(FMI_ME_OBJS:%= && (OMCFILE=% && cp $(RUNTIMEDIR)/$$OMCFILE.c $$OMCFILE.c))

fmu:
	rm -f 210.fmutmp/sources/Plant_init.xml
	cp -a "/usr/bin/../share/omc/runtime/c/fmi/buildproject/"* 210.fmutmp/sources
	cp -a Plant_FMU.libs 210.fmutmp/sources/

