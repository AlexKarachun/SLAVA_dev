from __future__ import annotations

from typing import Any, Optional


class LiberoContactTracker:
    """First-touch detection for a robosuite/MuJoCo LIBERO env.

    Heuristic, not ground truth — see slava-model-rollouts skill: the mandatory
    first-100-rollout manual audit from task.md is what actually validates this.
    """

    def __init__(self, env: Any, obj_body_id: dict[str, int]):
        self._sim = env.sim
        self._obj_body_id = obj_body_id
        self._body_id_to_sim_handle = {v: k for k, v in obj_body_id.items()}
        gripper = env.robots[0].gripper
        geoms: set[str] = set()
        for value in gripper.important_geoms.values():
            geoms.update(value)
        if not geoms:
            geoms.update(gripper.contact_geoms)
        self._gripper_geoms = geoms
        self.first_contact_object: Optional[str] = None
        self.forbidden_touched: set[str] = set()

    def step(self) -> None:
        sim = self._sim
        model = sim.model
        for i in range(sim.data.ncon):
            contact = sim.data.contact[i]
            name1 = model.geom_id2name(contact.geom1)
            name2 = model.geom_id2name(contact.geom2)
            if name1 is None or name2 is None:
                continue
            if name1 in self._gripper_geoms:
                other_geom = name2
            elif name2 in self._gripper_geoms:
                other_geom = name1
            else:
                continue
            other_geom_id = model.geom_name2id(other_geom)
            body_id = model.geom_bodyid[other_geom_id]
            sim_handle = self._body_id_to_sim_handle.get(body_id)
            if sim_handle is None:
                continue
            if self.first_contact_object is None:
                self.first_contact_object = sim_handle
            self.forbidden_touched.add(sim_handle)


class SimplerContactTracker:
    """First-touch detection for a SAPIEN/ManiSkill2 SimplerEnv env.

    Contacts are filtered by contact impulse. SAPIEN's `scene.get_contacts()`
    returns every contact PAIR the solver considered, including pairs that are
    merely touching/adjacent with no force transferred — so an unfiltered read
    registers a "touch" when the gripper passes close to an object without
    actually pushing it. ManiSkill2's own helpers never use the raw list for
    this: `get_pairwise_contact_impulse()` sums `point.impulse` over the
    contact's points and callers threshold the magnitude. We do the same, since
    `first_contact_object` feeds `wrong_object` and therefore
    `target_grounding_error` — a spuriously early first touch does not just add
    noise, it attributes the episode to the wrong object.
    """

    # Newton-seconds. Small enough to catch a light but real touch, large
    # enough to reject solver noise on a resting/near-miss pair. Same order of
    # magnitude ManiSkill2's own grasp checks use.
    IMPULSE_THRESHOLD = 1e-4

    def __init__(self, env: Any, actor_name_to_sim_handle: dict[str, str]):
        self._env = env
        self._actor_map = actor_name_to_sim_handle
        agent = env.agent
        gripper_link_names = {
            link.get_name()
            for link in agent.robot.get_links()
            if "finger" in link.get_name().lower() or "gripper" in link.get_name().lower()
        }
        if not gripper_link_names:
            # Silently empty here would mean "no contact is ever detected", and
            # every episode would land on no_action_or_timeout with no hint why.
            raise RuntimeError(
                "no gripper/finger links found on this robot: "
                f"{[l.get_name() for l in agent.robot.get_links()]}"
            )
        self._gripper_link_names = gripper_link_names
        self.first_contact_object: Optional[str] = None
        self.forbidden_touched: set[str] = set()

    def _impulse_magnitude(self, contact: Any) -> float:
        total = [0.0, 0.0, 0.0]
        for point in getattr(contact, "points", []):
            impulse = getattr(point, "impulse", None)
            if impulse is None:
                continue
            for i in range(3):
                total[i] += float(impulse[i])
        return (total[0] ** 2 + total[1] ** 2 + total[2] ** 2) ** 0.5

    def step(self) -> None:
        scene = self._env._scene
        for contact in scene.get_contacts():
            name0 = contact.actor0.get_name()
            name1 = contact.actor1.get_name()
            if name0 in self._gripper_link_names:
                other = name1
            elif name1 in self._gripper_link_names:
                other = name0
            else:
                continue
            sim_handle = self._actor_map.get(other)
            if sim_handle is None:
                continue
            if self._impulse_magnitude(contact) < self.IMPULSE_THRESHOLD:
                continue
            if self.first_contact_object is None:
                self.first_contact_object = sim_handle
            self.forbidden_touched.add(sim_handle)
