#!/usr/bin/env bash
# 40-users.sh — the separation that makes the rest of the design meaningful.
#
#   operator  : the human. wheel, can do anything, types the passphrase.
#   ultraos   : service user for ultraosd + harddenyd. No shell, no sudo.
#   approver  : owns the approval key, runs the approval UI. No sudo, no shell for AI.
#   ai        : where the AI process lives. No groups, no sudo, 0700 home, cannot read
#               /etc/ultraos/keys, cannot read the approver key, cannot touch /root.
set -Eeuo pipefail
[ "$(id -u)" -eq 0 ] || { echo "run as root" >&2; exit 1; }

echo "==> users"
id operator  >/dev/null 2>&1 || useradd -m -G wheel -s /bin/bash operator
id ultraos   >/dev/null 2>&1 || useradd -r -d /var/lib/ultraos -s /usr/bin/nologin ultraos
id approver  >/dev/null 2>&1 || useradd -r -d /var/lib/parametral -s /bin/bash approver
id ai        >/dev/null 2>&1 || useradd -m -s /bin/bash ai

# the AI account is deliberately naked: no supplementary groups, no sudo, no docker,
# no video/audio, no games. If a future step needs a group, that is a design change.
usermod -G "" ai
install -d -o ai -g ai -m 0700 /home/ai
install -d -o ultraos -g ultraos -m 0750 /var/lib/ultraos
install -d -o approver -g approver -m 0700 /var/lib/parametral
install -d -o root -g root -m 0700 /var/lib/parametral/keys

echo "==> passwords (interactive: operator types theirs, service users get none)"
passwd operator
passwd ai
usermod -L ultraos
usermod -L approver

echo "==> sudo: only wheel, and the AI accounts are explicitly denied"
cat > /etc/sudoers.d/10-parametral <<'EOF'
%wheel ALL=(ALL:ALL) ALL
ai       ALL=(ALL) !ALL
ultraos  ALL=(ALL) !ALL
approver ALL=(ALL) !ALL
EOF
chmod 0440 /etc/sudoers.d/10-parametral
visudo -cf /etc/sudoers.d/10-parametral

echo "==> polkit: the AI account cannot authorise privileged actions"
install -d -m 0755 /etc/polkit-1/rules.d
cat > /etc/polkit-1/rules.d/50-parametral-ai.rules <<'EOF'
// Parametral OS: the AI account may never obtain privileges through polkit.
polkit.addRule(function(action, subject) {
    if (subject.user === "ai") {
        return polkit.Result.NO;
    }
});
EOF

echo "==> directory ownership for the OS layer"
install -d -o root -g root -m 0755 /etc/ultraos
install -d -o root -g root -m 0755 /etc/ultraos/policy
install -d -o root -g root -m 0700 /etc/ultraos/keys
install -d -o root -g root -m 0755 /etc/parametral

echo "==> home permissions: other users cannot read each other"
chmod 0700 /home/ai /home/operator

echo "checks:"
printf '  ai groups: %s\n' "$(id -nG ai)"
printf '  ai sudo:   %s\n' "$(sudo -l -U ai 2>&1 | tail -1)"
