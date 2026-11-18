#!/bin/bash
# limit.sh <seconds> <what it is, for the message> <command ...>
#
# Runs the command. If it is still going after <seconds> it is stopped and the job fails, with an error that
# says what stalled. The downloads in the setup step now and then stall on the server's side (an Ubuntu mirror
# took half an hour over what takes seconds); left alone, the job waits out its whole time limit and is then
# "cancelled", which reads like nothing in particular. Stopped early it costs minutes, reads as what it is, and
# is a failure a re-run answers. Any other exit code of the command is passed on unchanged.
s=$1; what=$2; shift 2
if [ "$1" = sudo ]; then shift; set -- sudo timeout --kill-after=15 "$s" "$@"      # so the limit stops the command, not sudo
else set -- timeout --kill-after=15 "$s" "$@"; fi
"$@"
rc=$?
if [ "$rc" = 124 ] || [ "$rc" = 137 ]; then
  echo "::error title=Setup stalled::$what was not done after $((s / 60)) minutes and was stopped. That is the runner or the server it downloads from, not this change: run the job again."
fi
exit "$rc"
