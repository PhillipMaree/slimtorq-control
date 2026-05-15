# FIXME: before you push into master...
RUNTIMEDIR=/usr/bin/../include/omc/c/
#COPY_RUNTIMEFILES=$(FMI_ME_OBJS:%= && (OMCFILE=% && cp $(RUNTIMEDIR)/$$OMCFILE.c $$OMCFILE.c))

fmu:
	rm -f 230.fmutmp/sources/SlotlessPMSMPlant_init.xml
	cp -a "/usr/bin/../share/omc/runtime/c/fmi/buildproject/"* 230.fmutmp/sources
	cp -a SlotlessPMSMPlant_FMU.libs 230.fmutmp/sources/

