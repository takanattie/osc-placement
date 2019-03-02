# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from collections import defaultdict
import copy
import uuid

import six

from osc_placement.tests.functional import base


class TestInventory(base.BaseTestCase):
    def setUp(self):
        super(TestInventory, self).setUp()

        self.rp = self.resource_provider_create()

    def test_inventory_show(self):
        rp_uuid = self.rp['uuid']
        expected = {'min_unit': 1,
                    'max_unit': 12,
                    'reserved': 0,
                    'step_size': 1,
                    'total': 12,
                    'allocation_ratio': 16.0}

        args = ['VCPU:%s=%s' % (k, v) for k, v in expected.items()]
        self.resource_inventory_set(rp_uuid, *args)
        self.assertEqual(expected,
                         self.resource_inventory_show(rp_uuid, 'VCPU'))

    def test_inventory_show_not_found(self):
        rp_uuid = self.rp['uuid']

        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_show,
                                rp_uuid, 'VCPU')
        self.assertIn('No inventory of class VCPU for {}'.format(rp_uuid),
                      six.text_type(exc))

    def test_inventory_delete(self):
        rp_uuid = self.rp['uuid']

        self.resource_inventory_set(rp_uuid, 'VCPU=8')

        self.resource_inventory_delete(rp_uuid, 'VCPU')
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_show,
                                rp_uuid, 'VCPU')
        self.assertIn('No inventory of class VCPU for {}'.format(rp_uuid),
                      six.text_type(exc))

    def test_inventory_delete_not_found(self):
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_delete,
                                self.rp['uuid'], 'VCPU')
        self.assertIn('No inventory of class VCPU found for delete',
                      six.text_type(exc))

    def test_delete_all_inventories(self):
        # Negative test to assert command failure because
        # microversion < 1.5 and --resource-class is not specified.
        self.assertCommandFailed(
            base.ARGUMENTS_REQUIRED % '--resource-class',
            self.resource_inventory_delete,
            'fake_uuid')


class TestSetInventory(base.BaseTestCase):
    def test_fail_if_no_rp(self):
        exc = self.assertRaises(
            base.CommandException,
            self.openstack, 'resource provider inventory set')
        self.assertIn(base.ARGUMENTS_MISSING, six.text_type(exc))

    def test_set_empty_inventories(self):
        rp = self.resource_provider_create()
        self.assertEqual([], self.resource_inventory_set(rp['uuid']))

    def test_fail_if_incorrect_resource(self):
        rp = self.resource_provider_create()
        # wrong format
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                rp['uuid'], 'VCPU')
        self.assertIn('must have "name=value"', six.text_type(exc))
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                rp['uuid'], 'VCPU==')
        self.assertIn('must have "name=value"', six.text_type(exc))
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                rp['uuid'], '=10')
        self.assertIn('must be not empty', six.text_type(exc))
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                rp['uuid'], 'v=')
        self.assertIn('must be not empty', six.text_type(exc))

        # unknown class
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                rp['uuid'], 'UNKNOWN_CPU=16')
        self.assertIn('Unknown resource class', six.text_type(exc))
        # unknown property
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                rp['uuid'], 'VCPU:fake=16')
        self.assertIn('Unknown inventory field', six.text_type(exc))

    def test_set_multiple_classes(self):
        rp = self.resource_provider_create()
        resp = self.resource_inventory_set(
            rp['uuid'],
            'VCPU=8',
            'VCPU:max_unit=4',
            'MEMORY_MB=1024',
            'MEMORY_MB:reserved=256',
            'DISK_GB=16',
            'DISK_GB:allocation_ratio=1.5',
            'DISK_GB:min_unit=2',
            'DISK_GB:step_size=2')

        def check(inventories):
            self.assertEqual(8, inventories['VCPU']['total'])
            self.assertEqual(4, inventories['VCPU']['max_unit'])
            self.assertEqual(1024, inventories['MEMORY_MB']['total'])
            self.assertEqual(256, inventories['MEMORY_MB']['reserved'])
            self.assertEqual(16, inventories['DISK_GB']['total'])
            self.assertEqual(2, inventories['DISK_GB']['min_unit'])
            self.assertEqual(2, inventories['DISK_GB']['step_size'])
            self.assertEqual(1.5, inventories['DISK_GB']['allocation_ratio'])

        check({r['resource_class']: r for r in resp})
        resp = self.resource_inventory_list(rp['uuid'])
        check({r['resource_class']: r for r in resp})

    def test_set_known_and_unknown_class(self):
        rp = self.resource_provider_create()
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                rp['uuid'], 'VCPU=8', 'UNKNOWN=4')
        self.assertIn('Unknown resource class', six.text_type(exc))
        self.assertEqual([], self.resource_inventory_list(rp['uuid']))

    def test_replace_previous_values(self):
        """Test each new set call replaces previous inventories totally."""
        rp = self.resource_provider_create()
        # set disk inventory first
        self.resource_inventory_set(rp['uuid'], 'DISK_GB=16')
        # set memory and vcpu inventories
        self.resource_inventory_set(rp['uuid'], 'MEMORY_MB=16', 'VCPU=32')
        resp = self.resource_inventory_list(rp['uuid'])
        inv = {r['resource_class']: r for r in resp}
        # no disk inventory as it was overwritten
        self.assertNotIn('DISK_GB', inv)
        self.assertIn('VCPU', inv)
        self.assertIn('MEMORY_MB', inv)

    def test_delete_via_set(self):
        rp = self.resource_provider_create()
        self.resource_inventory_set(rp['uuid'], 'DISK_GB=16')
        self.resource_inventory_set(rp['uuid'])
        self.assertEqual([], self.resource_inventory_list(rp['uuid']))

    def test_fail_if_incorrect_parameters_set_class_inventory(self):
        exc = self.assertRaises(
            base.CommandException,
            self.openstack, 'resource provider inventory class set')
        self.assertIn(base.ARGUMENTS_MISSING, six.text_type(exc))
        exc = self.assertRaises(
            base.CommandException,
            self.openstack, 'resource provider inventory class set fake_uuid')
        self.assertIn(base.ARGUMENTS_MISSING, six.text_type(exc))
        exc = self.assertRaises(
            base.CommandException,
            self.openstack,
            ('resource provider inventory class set '
             'fake_uuid fake_class --total 5 --unknown 1'))
        self.assertIn('unrecognized arguments', six.text_type(exc))
        # Valid RP UUID and resource class, but no inventory field.
        rp = self.resource_provider_create()
        exc = self.assertRaises(
            base.CommandException, self.openstack,
            'resource provider inventory class set %s VCPU' % rp['uuid'])
        self.assertIn(base.ARGUMENTS_REQUIRED % '--total',
                      six.text_type(exc))

    def test_set_inventory_for_resource_class(self):
        rp = self.resource_provider_create()
        self.resource_inventory_set(rp['uuid'], 'MEMORY_MB=16', 'VCPU=32')
        self.resource_inventory_class_set(
            rp['uuid'], 'MEMORY_MB', total=128, step_size=16)
        resp = self.resource_inventory_list(rp['uuid'])
        inv = {r['resource_class']: r for r in resp}
        self.assertEqual(128, inv['MEMORY_MB']['total'])
        self.assertEqual(16, inv['MEMORY_MB']['step_size'])
        self.assertEqual(32, inv['VCPU']['total'])

    def test_fail_aggregate_arg_version_handling(self):
        agg = str(uuid.uuid4())
        self.assertCommandFailed(
            'Operation or argument is not supported with version 1.0; '
            'requires at least version 1.3',
            self.resource_inventory_set,
            agg, 'MEMORY_MB=16', aggregate=True)


class TestInventory15(TestInventory):
    VERSION = '1.5'

    def test_delete_all_inventories(self):
        rp = self.resource_provider_create()
        self.resource_inventory_set(rp['uuid'], 'MEMORY_MB=16', 'VCPU=32')
        self.resource_inventory_delete(rp['uuid'])
        self.assertEqual([], self.resource_inventory_list(rp['uuid']))


class TestAggregateInventory(base.BaseTestCase):
    VERSION = '1.3'

    def _get_expected_inventories(self, old_inventories, resources):
        new_inventories = []
        for old_inventory in old_inventories:
            new_inventory = defaultdict(dict)
            new_inventory.update(copy.deepcopy(old_inventory))
            for resource in resources:
                rc, keyval = resource.split(':')
                key, val = keyval.split('=')
                # Handle allocation ratio which is a float
                val = float(val) if '.' in val else int(val)
                new_inventory[rc][key] = val
                # The resource_class field is added by the osc_placement CLI,
                # so add it to our expected inventories
                if 'resource_class' not in new_inventory[rc]:
                    new_inventory[rc]['resource_class'] = rc
            new_inventories.append(new_inventory)
        return new_inventories

    def _setup_two_resource_providers_in_aggregate(self):
        rps = []
        inventory2 = ['VCPU=8',
                      'VCPU:max_unit=4',
                      'VCPU:allocation_ratio=16.0',
                      'MEMORY_MB=1024',
                      'MEMORY_MB:reserved=256',
                      'MEMORY_MB:allocation_ratio=2.5',
                      'DISK_GB=16',
                      'DISK_GB:allocation_ratio=1.5',
                      'DISK_GB:min_unit=2',
                      'DISK_GB:step_size=2']
        inventory1 = inventory2 + ['VGPU=8',
                                   'VGPU:allocation_ratio=1.0',
                                   'VGPU:min_unit=2',
                                   'VGPU:step_size=2']
        for i, inventory in enumerate([inventory1, inventory2]):
            rps.append(self.resource_provider_create())
            resp = self.resource_inventory_set(rps[i]['uuid'], *inventory)
            # Verify the resource_provider column is not present without
            # --aggregate
            self.assertNotIn('resource_provider', resp)
        # Put both resource providers in the same aggregate
        agg = str(uuid.uuid4())
        for rp in rps:
            self.resource_provider_aggregate_set(rp['uuid'], agg)
        return rps, agg

    def test_fail_if_no_rps_in_aggregate(self):
        nonexistent_agg = str(uuid.uuid4())
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                nonexistent_agg,
                                'VCPU=8',
                                aggregate=True)
        self.assertIn('No resource providers found in aggregate with uuid {}'
                      .format(nonexistent_agg), six.text_type(exc))

    def test_with_aggregate_one_fails(self):
        # Set up some existing inventories with two resource providers
        rps, agg = self._setup_two_resource_providers_in_aggregate()
        # Set a custom resource class inventory on the first resource provider
        self.resource_class_create('CUSTOM_FOO')
        rp1_uuid = rps[0]['uuid']
        rp1_inv = self.resource_inventory_set(rp1_uuid, 'CUSTOM_FOO=1')
        # Create an allocation for custom resource class on first provider
        consumer = str(uuid.uuid4())
        alloc = 'rp=%s,CUSTOM_FOO=1' % rp1_uuid
        self.resource_allocation_set(consumer, [alloc])
        # Try to set allocation ratio for an aggregate. The first set should
        # fail because we're not going to set the custom resource class (which
        # is equivalent to trying to remove it) and removal isn't allowed if
        # there is an allocation of it present. The second set should succeed
        new_resources = ['VCPU:allocation_ratio=5.0', 'VCPU:total=8']
        exc = self.assertRaises(base.CommandException,
                                self.resource_inventory_set,
                                agg, *new_resources, aggregate=True)
        self.assertIn('Failed to set inventory for 1 of 2 resource providers.',
                      six.text_type(exc))
        output = self.output.getvalue() + self.error.getvalue()
        err_txt = ("update conflict: Inventory for 'CUSTOM_FOO' on resource "
                   "provider '%s' in use. (HTTP 409)." % rp1_uuid)
        self.assertIn('Failed to set inventory for resource provider %s: %s' %
                      (rp1_uuid, err_txt), output)
        # Placement will default the following internally
        placement_defaults = ['VCPU:max_unit=2147483647',
                              'VCPU:min_unit=1',
                              'VCPU:reserved=0',
                              'VCPU:step_size=1']
        # Get expected inventory for the second resource provider (succeeded)
        new_inventories = self._get_expected_inventories(
            # Since inventories are expected to be fully replaced,
            # use empty dict for old inventory
            [{}],
            new_resources + placement_defaults)
        resp = self.resource_inventory_list(rps[1]['uuid'])
        self.assertDictEqual(new_inventories[0],
                             {r['resource_class']: r for r in resp})
        # First resource provider should have remained the same (failed)
        resp = self.resource_inventory_list(rp1_uuid)
        self.assertDictEqual({r['resource_class']: r for r in rp1_inv},
                             {r['resource_class']: r for r in resp})

    def test_with_aggregate(self):
        # Set up some existing inventories with two resource providers
        rps, agg = self._setup_two_resource_providers_in_aggregate()
        # Now, go ahead and update the allocation ratios and verify
        new_resources = ['VCPU:allocation_ratio=5.0',
                         'VCPU:total=8',
                         'MEMORY_MB:allocation_ratio=6.0',
                         'MEMORY_MB:total=1024',
                         'DISK_GB:allocation_ratio=7.0',
                         'DISK_GB:total=16']
        resp = self.resource_inventory_set(agg, *new_resources, aggregate=True)
        # Verify the resource_provider column is present with --aggregate
        for rp in resp:
            self.assertIn('resource_provider', rp)
        # Placement will default the following internally
        placement_defaults = ['VCPU:max_unit=2147483647',
                              'VCPU:min_unit=1',
                              'VCPU:reserved=0',
                              'VCPU:step_size=1',
                              'MEMORY_MB:max_unit=2147483647',
                              'MEMORY_MB:min_unit=1',
                              'MEMORY_MB:reserved=0',
                              'MEMORY_MB:step_size=1',
                              'DISK_GB:max_unit=2147483647',
                              'DISK_GB:min_unit=1',
                              'DISK_GB:reserved=0',
                              'DISK_GB:step_size=1']
        new_inventories = self._get_expected_inventories(
            # Since inventories are expected to be fully replaced,
            # use empty dicts for old inventories
            [{}, {}],
            new_resources + placement_defaults)
        for i in range(2):
            resp = self.resource_inventory_list(rps[i]['uuid'])
            self.assertDictEqual(new_inventories[i],
                                 {r['resource_class']: r for r in resp})
