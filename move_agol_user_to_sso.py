from arcgis.gis import GIS
from getpass import getpass
import os

# Get username and password
username = input('Connection username: ')
password = getpass(prompt='Connection password: ')

# Connect to ArcGIS Online
try:
    gis = GIS("https://cambridgegis.maps.arcgis.com/", username, password)
except:
    print(sys.exc_info()[0])
    exit(1)

# Get pointers to old and new users
agol_username = input('AGOL (old) username: ')

sso_username = input('SSO (new) username: ')

try:
    agol_user = gis.users.get(agol_username)
    sso_user = gis.users.get(sso_username)
except exceptions.Exception as e:
    print(f'Unexpected error: {e}')
    raise e

################
# Profile Items
################
print('Updating profile'.center(40,'-'))
# Even though the documentation says that you can pass a URL to the thumbnail input on the update method, it doesn't seem to work to pass the agol_user.get_thumbnail_link() result.
# Instead, I'm downloading the thumbnail and uploading it to the new account, which seems to work
agol_thumbnail_download = agol_user.download_thumbnail(os.getenv('TEMP'))
try:
    sso_user.update(access=agol_user.access, preferred_view=agol_user.preferredView, description=agol_user.description, tags=agol_user.tags, 
                    thumbnail=agol_thumbnail_download, fullname=agol_user.fullName, culture=agol_user.culture, region=agol_user.region, 
                    first_name=agol_user.firstName, last_name=agol_user.lastName)
except AttributeError:
    # Some old profiles don't seem to have firstName and lastName for some reason.  This was the only AttributError failure mode I encountered.  YMMV.
    sso_user.update(access=agol_user.access, preferred_view=agol_user.preferredView, description=agol_user.description, tags=agol_user.tags, 
                    thumbnail=agol_thumbnail_download, fullname=agol_user.fullName, culture=agol_user.culture, region=agol_user.region)

# Properties with separate methods # 
# Role #
# For built-in user roles (org_user, org_publisher, org_admin, viewer, view_only, viewplusedit) you can just use the role property for update_role
# but for custom roles you have to get the role object from the RoleManager static class (via gis.users.roles).
# You can't just use the second method for all of them because the built-in roles don't exist in the RoleManager.
builtin_roles = ['org_user', 'org_publisher', 'org_admin', 'viewer', 'view_only', 'viewplusedit']
if (agol_user.roleId in builtin_roles):
    sso_user.update_role(role=agol_user.roleId)
    print(agol_user.roleId, sso_user.roleId)
else:
    role = gis.users.roles.get_role(agol_user.roleId)
    sso_user.update_role(role=role)
    print(agol_user.roleId, sso_user.roleId, role.name)

# Regionalization #
sso_user.units = agol_user.units
sso_user.cultureFormat = agol_user.cultureFormat

# Esri access #
if (agol_user.esri_access == 'both'):
    sso_user.esri_access = True

#########
# Groups
#########
print('Updating groups'.center(40,'-'))
for group in agol_user.groups:
    try:
    if (group.owner == agol_username):
        print('Changing ownership: ' + group.title)
        group.reassign_to(sso_username)
    else:
        print('Joining: ' + group.title)
        group.add_users([sso_username])
    except Exception as e:
        print(e)

##########
# Content
##########
print('Moving content'.center(40,'-'))

# Function to reassign items, taking into account "Share and update capabilities"
# See 'Who can contribute content to the group?' in https://doc.arcgis.com/en/arcgis-online/share-maps/create-groups.htm for more details
all_groups = gis.groups.search('-')
update_groups = [group.title for group in all_groups if 'updateitemcontrol' in group.capabilities]
def item_reassign(item, user, folder=''):
    # Get a list of the item's groups
    item_groups = [group.title for group in item.shared_with['groups']]
    # See if any of them are restricted (configured to allow all members to update all items)
    item_update_groups = [title for title in item_groups if title in update_groups]
    # If so the item nees to be removed from those groups before it can be moved
    if item_update_groups:
        item.unshare(item_update_groups)
        
    try:
        # Do the move
        item.reassign_to(user, target_folder=folder)
    except Exception as e:
        print(e)
        raise e
    
    # Add the item back into the restricted groups (if applicable)
    if item_update_groups:
        item.share(groups=item_update_groups, allow_members_to_edit=True)

# Root Content #
agol_root_items = agol_user.items()
print('Folder: Root')
for item in agol_root_items:
    try:
        print('* Moving: ' + item.title)
        item_reassign(item=item, user=sso_username, folder=None)
    except Exception as e:
        print(e)
        print("Item may have already been assigned to user.")

# Folder Content #
agol_folders = agol_user.folders
sso_folders = sso_user.folders
sso_foldernames = [folder['title'] for folder in sso_folders]
for agol_folder in agol_folders:
    print('Folder: ' + agol_folder['title'])
    # In case script needs to be run twice for some reason, make sure the folder 
    # doesn't already exist before creating it
    if agol_folder['title'] not in sso_foldernames: 
        gis.content.create_folder(agol_folder['title'], sso_username)
    # Get a list of items from the source folder, then loop through and move each item
    agol_folder_items = agol_user.items(folder=agol_folder['title']) 
    for item in agol_folder_items:
        print('* Moving ' + item.title)
        try:
            item_reassign(item=item, user=sso_username, folder=agol_folder['title'])
        except Exception as e:
            print(e)
            print("Unable to reassign item " + item.title + " to folder " + agol_folder['title'])

####################
# Things we can't do
####################
# Favorites #
agol_fav_items = gis.groups.get(agol_user.favGroupId)
agol_favs = [content.title for content in agol_fav_items.content()]
if agol_favs:
    print("Old User's Favorites".center(40,'-'))
    print(agol_favs)


# Credits #
if (agol_user.assignedCredits > 100):
    print("Old User's Credits".center(40,'-'))
    print(f'Old user account had {agol_user.assignedCredits} credits')

# Licenses #
# Not yet available in AGOL #
# print("Old User's Licenses".center(40,'-'))
# print(agol_user.provisions)

#####################
# Disable old account
#####################
agol_user.disable()
