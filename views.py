from django.db.models.sql.constants import LOOKUP_SEP
from django.template import RequestContext
from django.shortcuts import render_to_response

from django_customreport.helpers import get_closest_relation, CustomReportDisplaySet
	
def results_view(queryset,display_fields=None):
	"""
	This is used in the custom_view below, but its de-coupled so it can be used
	programatically as well. Simply pass in a queryset and a list of relations to display
	and viola.
	
	Relations look like: ['address__zip','contact__date']

	"""
	display_fields = display_fields or []
	extra_select_kwargs = {}
	select_related = []
	for i in display_fields:
		if i in queryset.query.aggregates or i in queryset.query.extra:
			continue # Want below check to work only for relations, excluding aggregates. 

		select_related_token = i
		"""
		Since select_related() is rather flexible about what it receives
		(ignoring things it doesn't like), we'll just haphazardly pass 
		all filter and display fields in for now.
		"""

		if LOOKUP_SEP in i:
			select_related_token = i.split(LOOKUP_SEP)
			select_related_token.pop()
			select_related_token = LOOKUP_SEP.join(select_related_token)
			model, field, name = get_closest_relation(queryset.model,i)
		
			try:
				table = queryset.query.table_map[model._meta.db_table][-1] # The last join is probably(tm) right.
				queryset = queryset.extra(select={i: '%s.%s' % (table,field.column)})

			except KeyError:
				table = model._meta.db_table
				relation = None
				for r in model._meta.get_all_field_names():
					f = model._meta.get_field(r)
					if hasattr(f.rel,'to') and f.rel.to == queryset.model:
						rel = f.column
						break

				whereclause = '%s.id = %s.%s' % (queryset.model._meta.db_table,table,rel)

				queryset = queryset.extra(tables=[table],where=[whereclause],select={i: '%s.%s' % (table,field.column)})

		select_related.append(select_related_token)

	queryset = queryset.select_related(*select_related)
	return queryset

class custom_view(object):
	def __new__(cls, request, *args, **kwargs):
		obj = super(custom_view, cls).__new__(cls)
		return obj(request, *args, **kwargs)

	def __call__(cls,request,queryset=None,template_name=None,extra_context=None,form=None):
		cls.template_name = template_name
		cls.request = request
		cls.queryset = queryset
		cls.extra_context = extra_context or {}

		pre_form = cls.get_pre_form(request)
		if request.GET:
			if not 'custom_token' in request.GET:
				pre_form = cls.get_pre_form(request)
				if pre_form.is_valid():
					return cls.render_post_form(display_fields=pre_form.cleaned_data['display_fields'],\
							filter_fields=pre_form.cleaned_data['filter_fields'])
			else:
				return cls.render_post_form(display_fields=request.GET.get('display_fields'),filter_fields=request.GET.get('filter_fields'))

		return cls.fallback(pre_form=pre_form)

	def get_post_form(self):
		"""
		Meant to be overridden.

		This form is an all-inclusive form with all possible field options attached.
		Fields not selected in the pre-form are deleted from this form and you're
		left with a subset of the original fields.
		"""

		return self.post_form

	def get_pre_form(self,request):
		"""
		Meant to be overridden.

		A pre-form has two required fields: 'display_fields' and 'filter_fields'.

		They are meant to be MultipleChoiceFields and the result is used to modify
		the post form. Any fields not found in the pre-form data are deleted from the
		post form fields.
		"""

		return self.pre_form

	def fallback(self,pre_form=None,post_form=None,display_fields=None):
		display_fields = display_fields or []
		c = {'pre_form': pre_form, 'post_form': post_form, 'display_fields': display_fields,\
				'custom_token': self.request.GET.get('custom_token',False) }

		c.update(self.extra_context or {})
		return render_to_response(self.template_name, c, context_instance=RequestContext(self.request))

	def render_post_form(self,display_fields=None,filter_fields=None):
		display_fields = display_fields or []
		filter_fields = filter_fields or []

		form = self.get_post_form()

		display_fields = self.request.GET.getlist('display_fields')	
		filter_fields = self.request.GET.getlist('filter_fields')	

		kept_fields = form.fields.copy()
		for i in form.fields:
			if not i in filter_fields:
				del kept_fields[i]

		form.fields = kept_fields
	
		from django import forms
		form.fields['display_fields'] = forms.MultipleChoiceField(choices=[(i,i) for i in display_fields],required=False)
		form.fields['filter_fields'] = forms.MultipleChoiceField(choices=[(i,i) for i in filter_fields])

		form.initial['display_fields'] = self.request.GET.get('display_fields') # hacky...
		form.initial['filter_fields'] = self.request.GET['filter_fields'] # hacky, breaks with pre. todo.

		if 'custom_token' in self.request.GET and form.is_valid():
			queryset = self.queryset
			from django.db.models.query import QuerySet
			if not isinstance(self.queryset,QuerySet): # it was passed in above
				queryset = self.filter.queryset

			return self.render_results(queryset,display_fields=display_fields + filter_fields)

		return self.fallback(post_form=form,display_fields=display_fields)

	def render_results(self,queryset,display_fields = None):
		return results_view(queryset,display_fields=display_fields)

class displayset_view(custom_view):
	"""
	This is a convenience view which will accept five additional arguments.

	1) filter_class - this will build your queryset for you

	http://github.com/alex/django-filter

	If you only want to use one of the above, just subclass and override.

	
	2) displayset_class  - this will easily render your results to an admin-like interface

	http://github.com/subsume/django-displayset

	3) change_list_template - this is the template used ablove

	"""
	def __call__(cls, filter_class, displayset_class, request, queryset=None,\
			change_list_template='customreport/base.html',exclusions=None,depth=None,*args, **kwargs):
		cls.filter_class = filter_class
		cls.filter = filter_class(request.GET or None,queryset=queryset)
		cls.exclusions = exclusions
		cls.depth = depth
		cls.change_list_template = change_list_template
		cls.displayset_class = displayset_class
		return custom_view.__call__(cls,request,queryset=queryset,extra_context={'filter': cls.filter},*args,**kwargs)

	def get_post_form(self):
		return self.filter.form

	def get_pre_form(self,request):
		from django_customreport.forms import FilterSetCustomPreForm
		return FilterSetCustomPreForm(self.filter,request.GET or None,depth=self.depth,exclusions=self.exclusions)

	def render_post_form(self,**kwargs):
		kept_filters = self.filter.filters.copy()
		for i in self.filter.filters:
			if not i in kwargs.get('filter_fields',[]):
				del kept_filters[i]

		self.filter.filters = kept_filters
		return super(displayset_view,self).render_post_form(**kwargs)

	def render_results(self,queryset,display_fields=None):
		queryset = super(displayset_view,self).render_results(queryset)
		filter = self.filter_class(self.request.GET,queryset=queryset)
		filter.get_parameters = {}
		
		self.displayset_class.display_fields = display_fields
		self.displayset_class.change_list_template = self.change_list_template
		from django_displayset import views as displayset_views
		return displayset_views.generic(self.request,filter.qs,self.displayset_class,\
						extra_context={'filter': filter})
