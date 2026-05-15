# FIXME: before you push into master...
RUNTIMEDIR=/usr/bin/../include/omc/c/
#COPY_RUNTIMEFILES=$(FMI_ME_OBJS:%= && (OMCFILE=% && cp $(RUNTIMEDIR)/$$OMCFILE.c $$OMCFILE.c))

fmu:
	rm -f 428.fmutmp/sources/SlotlessPMSM_init.xml
	cp -a "/usr/bin/../share/omc/runtime/c/fmi/buildproject/"* 428.fmutmp/sources
	cp -a SlotlessPMSM_FMU.libs 428.fmutmp/sources/

