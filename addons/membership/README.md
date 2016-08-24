# Membership

This repository contains the membership addons with modifications for PolyFab.
Right now, it only adds qualifications for each member.
Here are some features that would be interesting to add:

* [ ] Member should have qualifications for a set of machines.
      A qualification expires after a certain amount of time. After expiration, a new qualification for the member can be created and appears as a new line in the list of qualifications.
* [x] Membership product should be generics.
      An administrator would not need to create a membership product for each time a member buys a membership.
      Only the duration and the cost of the membership product should be specified.
      The validation of the membership for the user would be computed on the fly.
* [ ] Member should be able to check in. The application for check-in should be a web-based API that look into the database and display appropriate informations.
      Each time a member checks in, we could show the status of his membership and his qualifications, and a list of machines he can use.
* [ ] Administrator should be able to see an history of the all the check-ins.

Installation
------------

The installation is straightforward if we assume that a clean Odoo server is already setup.

1. Go in the `addons` folder of the Odoo installation
2. Delete/Backup the folder called `membership`
3. Clone this repository inside the `addons` folder

The installation process might look like this: 

```
  $ cd "addons"
  $ mv "membership" "../membership-backup"
  $ git clone https://github.com/TheNiceGuy/membership.git
```

After the installation is done, you should start/restart the Odoo server.
Then, update the addons in the Odoo settings and install the membership module.

Updating
--------

By cloning this repository, we can easily get small updates/fixes by simply pulling the latest commits:

```
  $ cd "addons/membership"
  $ git pull
```

Developping
-----------

In order to contribute to this fork, you must first clone this repository and install the Odoo server with the module.
When commiting, you must be sure that it does the not break the current Odoo models of this module.
When ready, send a pull request for reviewing.
For now, this repository should always contains a "clean" version ready to update.

