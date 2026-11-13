import logging
import subprocess

log = logging.getLogger(__name__)

TARGET = "cass1"  # VM10's node will be faulted
SCRIPT = "~/fault-injection.sh"
TIMEOUT_SECONDS = 150


class FaultInjector:
    def __init__(self, ssh_target):
        self._ssh_target = ssh_target

    def _run(self, *args):
        if not self._ssh_target:
            raise RuntimeError("FAULT_SSH_TARGET is not set")
        
        command = ["ssh", "-o", "BatchMode=yes", self._ssh_target, SCRIPT, *args]
        log.info("fault command: %s", " ".join(command))
        subprocess.run(command, check=True, timeout=TIMEOUT_SECONDS)

    def apply(self, config):
        active = []
        delay = config["delay_ms"]
        loss = config["packet_loss_pct"]
        if delay or loss:
            self._run("netem", f"{delay}ms", f"{loss}%")
            if delay:
                active.append({"kind": "delay", "target": TARGET,"value": delay})
            if loss:
                active.append({"kind": "packet_loss", "target": TARGET, "value": loss})
        if config["node_outage"] == "one_node_down":
            self._run("down")
            active.append({"kind": "node_down", "target": TARGET, "value": None})
        return active

    def clear(self, active):
        if not active:
            return

        kinds = {fault["kind"] for fault in active}
        if "node_down" in kinds:
            self._run("up")
        if "delay" in kinds or "packet_loss" in kinds:
            self._run("clear")
